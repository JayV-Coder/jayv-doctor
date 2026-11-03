"""Conector do Google Cloud Logging: `entries.list` em ordem de timestamp, com janela até
agora-30 s e Checkpoint (timestamp, insertId). Ao retomar, pede a partir de Checkpoint-30 s (as
entradas chegam ao Logging com atraso); a deduplicação por event_id da ingestão descarta as
repetidas. Respeita a cota de leitura da API, também entre tentativas, e trata
RESOURCE_EXHAUSTED como 429."""

import asyncio
import re
import time
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
SERVICE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
SEVERITIES = ("DEBUG", "INFO", "NOTICE", "WARNING", "ERROR", "CRITICAL", "ALERT", "EMERGENCY")
PERMISSION = "logging.logEntries.list"


def rfc3339(moment: datetime) -> str:
    base = moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S")
    return f"{base}.{moment.microsecond:06d}Z" if moment.microsecond else f"{base}Z"


def parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def balanced(query: str) -> bool:
    """Parênteses fechados na ordem, fora de aspas: a consulta do cliente fica dentro dos dela e
    não escapa para afrouxar a janela de tempo (`a) OR (b`)."""
    depth, quoted, escaped = 0, False, False
    for char in query:
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == '"':
            quoted = not quoted
        elif not quoted and char == "(":
            depth += 1
        elif not quoted and char == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0 and not quoted


def denial(response: httpx.Response, project: str, account: str) -> str:
    """O motivo do 403: API desativada, ou falta de permissão (dizendo qual, para quem e onde)."""
    try:
        error = response.json().get("error", {})
    except ValueError:
        error = {}
    details = error.get("details", []) if isinstance(error, dict) else []
    reasons = {str(item.get("reason")) for item in details if isinstance(item, dict)}
    text = str(error.get("message", "")) if isinstance(error, dict) else ""
    if "SERVICE_DISABLED" in reasons or "has not been used" in text or "is disabled" in text:
        return (
            f"A API do Cloud Logging está desativada no projeto {project}: "
            "ative-a no console do Google Cloud."
        )
    return (
        f"A Service Account {account} não tem a permissão {PERMISSION} "
        f"no projeto {project}: conceda o papel roles/logging.viewer."
    )


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
        # Reaproveitados entre as tentativas do runtime na mesma Sincronização.
        self.token: tuple[str, float] | None = None
        self.last_request: float | None = None

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=self.transport, timeout=httpx.Timeout(30.0))

    def validate_config(self, config: Mapping[str, Any]) -> ConfigErrors:
        errors: ConfigErrors = {}
        if not PROJECT.match(str(config.get("project_id", ""))):
            errors["project_id"] = "id do projeto GCP"
        if config.get("auth", "key") != "key":
            errors["auth"] = "key (o modo sem chave ainda não está disponível)"
        services = config.get("services", [])
        if not isinstance(services, list) or not all(SERVICE.match(str(s)) for s in services):
            errors["services"] = "lista de serviços do Cloud Run"
        if config.get("min_severity", "DEFAULT") not in ("DEFAULT", *SEVERITIES):
            errors["min_severity"] = "severidade do Logging"
        query = config.get("filter", "")
        if not isinstance(query, str) or len(query) > 2000 or not balanced(query):
            errors["filter"] = "consulta do Logging com até 2000 caracteres e parênteses fechados"
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

    async def bearer(self, client: httpx.AsyncClient, secret: Secret) -> str:
        if self.token is None or self.token[1] < time.monotonic() + 60:
            token, seconds = await access_token(client, secret)
            self.token = (token, time.monotonic() + seconds)
        return self.token[0]

    async def pace(self, config: Mapping[str, Any]) -> None:
        """Espaça as chamadas pela cota, também entre tentativas da mesma Sincronização."""
        interval = 60.0 / int(config.get("requests_per_minute", 60))
        if self.last_request is not None:
            wait = interval - (time.monotonic() - self.last_request)
            if wait > 0:
                await self.sleep(round(wait, 1))
        self.last_request = time.monotonic()

    async def entries(
        self,
        client: httpx.AsyncClient,
        secret: Secret,
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
        token = await self.bearer(client, secret)
        await self.pace(config)
        try:
            response = await client.post(
                ENTRIES, json=body, headers={"authorization": f"Bearer {token}"}
            )
        except httpx.HTTPError as exc:
            raise ConnectorError("transient", "O Cloud Logging não respondeu.") from exc
        if response.status_code == 200:
            try:
                found = response.json()
            except ValueError as exc:
                raise ConnectorError("transient", "Resposta inesperada do Cloud Logging.") from exc
            return found if isinstance(found, dict) else {}
        if response.status_code == 429:
            raise ConnectorError("rate_limit", "Cota de leitura do Cloud Logging esgotada.", 60)
        if response.status_code == 401:
            raise ConnectorError("auth", "O Google recusou a credencial.")
        if response.status_code == 403:
            message = denial(response, str(config["project_id"]), principal(secret))
            raise ConnectorError("auth", message)
        if response.status_code in (400, 404):
            raise ConnectorError("invalid", "Projeto ou consulta do Logging inválidos.")
        raise ConnectorError("transient", f"Cloud Logging respondeu HTTP {response.status_code}.")

    async def test_connection(self, secret: Secret, config: Mapping[str, Any]) -> TestResult:
        try:
            async with self.client() as client:
                now = self.clock()
                await self.entries(
                    client, secret, config, self.query(config, now - OVERLAP, now), None, 1
                )
        except ConnectorError as exc:
            return TestResult(False, exc.message)
        return TestResult(True, "Conexão estabelecida: a Service Account lê os logs do projeto.")

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
        page_size = int(config.get("page_size", 1000))
        window = rfc3339(until)
        async with self.client() as client:
            page_token: str | None = None
            page = 0
            while True:
                response = await self.entries(client, secret, config, query, page_token, page_size)
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
