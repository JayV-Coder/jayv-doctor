"""Conector do Google Cloud Logging: `entries.list` em ordem de timestamp, com janela até
agora-30 s e Checkpoint (timestamp, insertId). Ao retomar, pede a partir de Checkpoint-30 s (as
entradas chegam ao Logging com atraso); a deduplicação por event_id da ingestão descarta as
repetidas. Respeita a cota de leitura da API e trata RESOURCE_EXHAUSTED como 429."""

import asyncio
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

import httpx

from aid_connectors.base import (
    Batch,
    Checkpoint,
    ConfigErrors,
    ConnectorError,
    RateLimitPolicy,
    Secret,
    TestResult,
)
from aid_connectors.gcp.auth import access_token, principal
from aid_connectors.gcp.mapping import timestamp, to_event

ENTRIES = "https://logging.googleapis.com/v2/entries:list"
OVERLAP = timedelta(seconds=30)
PROJECT = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.iam\.gserviceaccount\.com$")
SERVICE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
SEVERITIES = ("DEBUG", "INFO", "NOTICE", "WARNING", "ERROR", "CRITICAL", "ALERT", "EMERGENCY")
PERMISSION = "logging.logEntries.list"


def rfc3339(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S") + (
        f".{moment.microsecond:06d}Z" if moment.microsecond else "Z"
    )


def parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class GcpLoggingConnector:
    provider: ClassVar[str] = "gcp"
    # Cota padrão da API de leitura do Logging: 60 req/min por projeto.
    rate_limit: ClassVar[RateLimitPolicy] = RateLimitPolicy(requests_per_minute=60)

    def __init__(
        self,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.transport = transport
        self.clock = clock
        self.sleep = sleep

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=self.transport, timeout=httpx.Timeout(30.0))

    def validate_config(self, config: Mapping[str, Any]) -> ConfigErrors:
        errors: ConfigErrors = {}
        if not PROJECT.match(str(config.get("project_id", ""))):
            errors["project_id"] = "id do projeto GCP"
        if config.get("auth", "key") not in ("key", "impersonation"):
            errors["auth"] = "key ou impersonation"
        if config.get("auth") == "impersonation" and not EMAIL.match(
            str(config.get("service_account", ""))
        ):
            errors["service_account"] = "e-mail da Service Account do cliente"
        services = config.get("services", [])
        if not isinstance(services, list) or not all(SERVICE.match(str(s)) for s in services):
            errors["services"] = "lista de serviços do Cloud Run"
        if config.get("min_severity", "DEFAULT") not in ("DEFAULT", *SEVERITIES):
            errors["min_severity"] = "severidade do Logging"
        if not isinstance(config.get("filter", ""), str) or len(config.get("filter", "")) > 2000:
            errors["filter"] = "consulta do Logging com até 2000 caracteres"
        if config.get("backfill_hours", 24) not in (24, 168):
            errors["backfill_hours"] = "24 ou 168"
        rpm = config.get("requests_per_minute", 60)
        if not isinstance(rpm, int) or not 1 <= rpm <= 600:
            errors["requests_per_minute"] = "de 1 a 600"
        page = config.get("page_size", 1000)
        if not isinstance(page, int) or not 1 <= page <= 1000:
            errors["page_size"] = "de 1 a 1000"
        return errors

    def query(self, config: Mapping[str, Any], start: datetime, until: datetime) -> str:
        parts = [f'timestamp >= "{rfc3339(start)}"', f'timestamp < "{rfc3339(until)}"']
        services = config.get("services") or []
        if services:
            names = " OR ".join(f'"{service}"' for service in services)
            parts.append('resource.type="cloud_run_revision"')
            parts.append(f"resource.labels.service_name=({names})")
        if config.get("min_severity", "DEFAULT") != "DEFAULT":
            parts.append(f"severity >= {config['min_severity']}")
        if config.get("filter"):
            parts.append(f"({config['filter']})")
        return " AND ".join(parts)

    async def entries(
        self,
        client: httpx.AsyncClient,
        token: str,
        config: Mapping[str, Any],
        query: str,
        page_token: str | None,
        page_size: int,
    ) -> Mapping[str, Any]:
        body: dict[str, Any] = {
            "resourceNames": [f"projects/{config['project_id']}"],
            "filter": query,
            "orderBy": "timestamp asc",
            "pageSize": page_size,
        }
        if page_token:
            body["pageToken"] = page_token
        try:
            response = await client.post(
                ENTRIES, json=body, headers={"authorization": f"Bearer {token}"}
            )
        except httpx.HTTPError as exc:
            raise ConnectorError("transient", "O Cloud Logging não respondeu.") from exc
        if response.status_code == 200:
            return response.json() or {}
        if response.status_code == 429:
            raise ConnectorError("rate_limit", "Cota de leitura do Cloud Logging esgotada.", 60)
        if response.status_code == 401:
            raise ConnectorError("auth", "O Google recusou a credencial.")
        if response.status_code == 403:
            raise ConnectorError("auth", PERMISSION)
        if response.status_code in (400, 404):
            raise ConnectorError("invalid", "Projeto ou consulta do Logging inválidos.")
        raise ConnectorError("transient", f"Cloud Logging respondeu HTTP {response.status_code}.")

    async def test_connection(self, secret: Secret, config: Mapping[str, Any]) -> TestResult:
        try:
            async with self.client() as client:
                token = await access_token(client, secret, config)
                now = self.clock()
                await self.entries(
                    client, token, config, self.query(config, now - OVERLAP, now), None, 1
                )
        except ConnectorError as exc:
            if exc.message == PERMISSION:
                return TestResult(False, self.missing_permission(secret, config))
            return TestResult(False, exc.message)
        return TestResult(True, "Conexão estabelecida: a Service Account lê os logs do projeto.")

    def missing_permission(self, secret: Secret, config: Mapping[str, Any]) -> str:
        return (
            f"A Service Account {principal(secret, config)} não tem a permissão {PERMISSION} "
            f"no projeto {config['project_id']}: conceda o papel roles/logging.viewer."
        )

    async def collect(
        self, secret: Secret, config: Mapping[str, Any], checkpoint: Checkpoint | None
    ) -> AsyncIterator[Batch]:
        now = self.clock()
        until = now - OVERLAP
        if checkpoint and checkpoint.get("timestamp"):
            start = parse(str(checkpoint["timestamp"])) - OVERLAP
        else:
            start = now - timedelta(hours=int(config.get("backfill_hours", 24)))
        query = self.query(config, start, until)
        pause = 60.0 / int(config.get("requests_per_minute", 60))
        page_size = int(config.get("page_size", 1000))
        window = rfc3339(until)
        async with self.client() as client:
            token = await access_token(client, secret, config)
            page_token: str | None = None
            page = 0
            while True:
                if page:
                    await self.sleep(pause)
                try:
                    response = await self.entries(
                        client, token, config, query, page_token, page_size
                    )
                except ConnectorError as exc:
                    if exc.message == PERMISSION:
                        raise ConnectorError(
                            "auth", self.missing_permission(secret, config)
                        ) from exc
                    raise
                page += 1
                found = response.get("entries") or []
                if found:
                    last = found[-1]
                    yield Batch(
                        [to_event(entry) for entry in found],
                        {
                            "timestamp": rfc3339(timestamp(str(last["timestamp"]))),
                            "insert_id": last.get("insertId"),
                            "until": window,
                            "page": page,
                        },
                    )
                page_token = response.get("nextPageToken")
                if not page_token:
                    break
        # Janela inteira lida: a próxima começa em `until` (menos a sobreposição).
        yield Batch([], {"timestamp": window, "insert_id": None, "until": window, "page": "fim"})
