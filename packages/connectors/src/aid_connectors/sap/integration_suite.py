"""SAP Integration Suite (Cloud Integration), ticket #38 fase B: os Message Processing Logs
(`/api/v1/MessageProcessingLogs`, OData v2) viram Eventos correlacionáveis pelo `CorrelationId`.

- **Credencial:** a service key do plano `api` do Process Integration Runtime
  (`{"client_id", "client_secret"}`), trocada por token com OAuth client credentials. Token e API
  só em hosts da SAP BTP (`*.hana.ondemand.com`, `*.cloud.sap`), nunca num endereço qualquer
  da config (SSRF); o E2E troca por loopback.
- **Checkpoint:** (`LogEnd`, `MessageGuid`), com desempate pelo Guid no mesmo instante.
- **Filtro:** por padrão só os que falharam (`FAILED`, `ESCALATED`, `RETRY`); `COMPLETED`
  entra com `include_completed`, para a Execução mostrar o sucesso também.
"""

import asyncio
import json
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar
from urllib.parse import urlparse

import httpx

from aid_connectors.base import (
    Batch,
    Checkpoint,
    ConfigErrors,
    ConnectorError,
    RateLimitPolicy,
    Secret,
    TestResult,
    stable_uuid7,
)
from aid_connectors.common import is_loopback

BTP_HOST = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)*\.(hana\.ondemand\.com|cloud\.sap)$")
GUID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
ODATA_DATE = re.compile(r"/Date\((-?\d+)(?:[+-]\d+)?\)/")
FAILED = ("FAILED", "ESCALATED", "RETRY")
SEVERITY = {"FAILED": "ERROR", "ESCALATED": "CRITICAL", "RETRY": "WARNING", "COMPLETED": "INFO"}
FIELDS = (
    "MessageGuid,CorrelationId,ApplicationMessageId,LogStart,LogEnd,Status,CustomStatus,"
    "IntegrationFlowName,Sender,Receiver"
)


def trusted(url: str, *, path: str | None = None) -> bool:
    if is_loopback(url):
        return True
    parsed = urlparse(url)
    return (
        parsed.scheme == "https"
        and BTP_HOST.match(parsed.hostname or "") is not None
        and parsed.username is None
        and (path is None or parsed.path.rstrip("/") == path)
    )


def odata_date(value: Any) -> datetime:
    """`/Date(1731247500000)/` (OData v2) ou ISO 8601."""
    text = str(value)
    found = ODATA_DATE.match(text)
    if found:
        return datetime.fromtimestamp(int(found[1]) / 1000, UTC)
    moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def literal(moment: datetime) -> str:
    return "datetime'" + moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "'"


def to_event(log: Mapping[str, Any]) -> dict[str, Any]:
    status = str(log.get("Status", "")).upper()
    at = odata_date(log.get("LogEnd") or log.get("LogStart"))
    flow = str(log.get("IntegrationFlowName") or "integration-flow")[:128]
    event: dict[str, Any] = {
        "schema_version": "1.0",
        "event_id": stable_uuid7(f"sap-cpi:{log['MessageGuid']}", at),
        "timestamp": at.isoformat(),
        "source": {"provider": "sap", "service": "integration-suite", "resource": flow[:256]},
        "operation": flow,
        "severity": SEVERITY.get(status, "INFO"),
        "attributes": {
            "sap_cpi_message_guid": str(log["MessageGuid"])[:200],
            "sap_cpi_status": status[:200],
            **{
                name: str(log[key])[:200]
                for name, key in (
                    ("sap_cpi_sender", "Sender"),
                    ("sap_cpi_receiver", "Receiver"),
                    ("application_message_id", "ApplicationMessageId"),
                    ("sap_cpi_custom_status", "CustomStatus"),
                )
                if log.get(key)
            },
        },
    }
    if log.get("CorrelationId"):
        event["execution_id"] = str(log["CorrelationId"])[:256]
    if status in FAILED:
        detail = log.get("CustomStatus") or status
        event["error"] = {"category": "UNKNOWN", "message": f"iFlow {flow}: {detail}"[:8192]}
    return event


class SapIntegrationSuiteConnector:
    provider: ClassVar[str] = "sap"
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
        self.token: tuple[str, float] | None = None
        self.last_request: float | None = None

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=self.transport, timeout=httpx.Timeout(30.0))

    def validate_config(self, config: Mapping[str, Any]) -> ConfigErrors:
        errors: ConfigErrors = {}
        if config.get("product", "integration_suite") != "integration_suite":
            errors["product"] = "integration_suite"
        if not trusted(str(config.get("api_url", ""))):
            errors["api_url"] = "URL https da API do Cloud Integration (*.hana.ondemand.com)"
        if not trusted(str(config.get("token_url", "")), path="/oauth/token"):
            errors["token_url"] = "URL https do token da SAP BTP (…/oauth/token)"  # noqa: S105
        if not isinstance(config.get("include_completed", False), bool):
            errors["include_completed"] = "true ou false"
        if config.get("backfill_hours", 24) not in (24, 168):
            errors["backfill_hours"] = "24 ou 168"
        page = config.get("page_size", 200)
        if not isinstance(page, int) or not 1 <= page <= 1000:
            errors["page_size"] = "de 1 a 1000"
        rpm = config.get("requests_per_minute", 60)
        if not isinstance(rpm, int) or not 1 <= rpm <= 600:
            errors["requests_per_minute"] = "de 1 a 600"
        return errors

    async def bearer(
        self, client: httpx.AsyncClient, secret: Secret, config: Mapping[str, Any]
    ) -> str:
        if self.token is not None and self.token[1] > time.monotonic() + 60:
            return self.token[0]
        try:
            info = json.loads(secret.reveal())
            client_id, client_secret = str(info["client_id"]), str(info["client_secret"])
        except (ValueError, KeyError, TypeError) as exc:
            raise ConnectorError("auth", "A credencial não é uma service key da SAP BTP.") from exc
        try:
            response = await client.post(
                str(config["token_url"]),
                data={"grant_type": "client_credentials"},
                auth=(client_id, client_secret),
            )
        except httpx.HTTPError as exc:
            raise ConnectorError(
                "transient", "A SAP BTP não respondeu ao pedido de token."
            ) from exc
        if response.status_code in (400, 401):
            raise ConnectorError("auth", "A SAP BTP recusou a service key.")
        try:
            body = response.json()
            self.token = (
                str(body["access_token"]),
                time.monotonic() + float(body.get("expires_in", 3600)),
            )
        except (ValueError, KeyError) as exc:
            raise ConnectorError(
                "transient", "Resposta inesperada da SAP BTP ao pedir o token."
            ) from exc
        return self.token[0]

    async def pace(self, config: Mapping[str, Any]) -> None:
        interval = 60.0 / int(config.get("requests_per_minute", 60))
        if self.last_request is not None:
            wait = interval - (time.monotonic() - self.last_request)
            if wait > 0:
                await self.sleep(round(wait, 1))
        self.last_request = time.monotonic()

    def query(
        self,
        config: Mapping[str, Any],
        after: tuple[datetime, str] | None,
        start: datetime,
        top: int,
    ) -> dict[str, str]:
        statuses = [*FAILED, *(["COMPLETED"] if config.get("include_completed") else [])]
        status = " or ".join(f"Status eq '{s}'" for s in statuses)
        if after is not None:
            moment, guid = after
            if not GUID.match(guid):
                raise ConnectorError("invalid", "Checkpoint inválido.")
            window = (
                f"(LogEnd gt {literal(moment)} or (LogEnd eq {literal(moment)}"
                f" and MessageGuid gt '{guid}'))"
            )
        else:
            window = f"LogEnd ge {literal(start)}"
        return {
            "$filter": f"({status}) and {window}",
            "$orderby": "LogEnd,MessageGuid",
            "$top": str(top),
            "$select": FIELDS,
            "$format": "json",
        }

    async def logs(
        self,
        client: httpx.AsyncClient,
        secret: Secret,
        config: Mapping[str, Any],
        params: Mapping[str, str],
    ) -> list[Mapping[str, Any]]:
        token = await self.bearer(client, secret, config)
        await self.pace(config)
        url = f"{str(config['api_url']).rstrip('/')}/api/v1/MessageProcessingLogs"
        try:
            response = await client.get(
                url, params=params, headers={"authorization": f"Bearer {token}"}
            )
        except httpx.HTTPError as exc:
            raise ConnectorError("transient", "O Cloud Integration não respondeu.") from exc
        if response.status_code == 401:
            self.token = None
            raise ConnectorError("auth", "O Cloud Integration recusou o token.")
        if response.status_code == 403:
            raise ConnectorError(
                "auth", "A service key não tem o papel de leitura dos logs (MonitoringDataRead)."
            )
        if response.status_code == 429:
            raise ConnectorError("rate_limit", "O Cloud Integration limitou as chamadas.", 60)
        if response.status_code in (400, 404):
            raise ConnectorError(
                "invalid", "URL da API ou consulta recusadas pelo Cloud Integration."
            )
        if response.status_code != 200:
            raise ConnectorError(
                "transient", f"O Cloud Integration respondeu HTTP {response.status_code}."
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise ConnectorError("transient", "Resposta inesperada do Cloud Integration.") from exc
        found = (body.get("d") or {}).get("results", []) if isinstance(body, dict) else []
        return [item for item in found if isinstance(item, Mapping) and item.get("MessageGuid")]

    async def test_connection(
        self, secret: Secret, config: Mapping[str, Any], *, preview: bool = False
    ) -> TestResult:
        try:
            async with self.client() as client:
                start = self.clock() - timedelta(hours=24)
                found = await self.logs(
                    client, secret, config, self.query(config, None, start, 100 if preview else 1)
                )
        except ConnectorError as exc:
            return TestResult(False, exc.message)
        if not preview:
            return TestResult(
                True, "Conexão estabelecida: a service key lê os logs do Cloud Integration."
            )
        amount = f"{'100 ou mais' if len(found) >= 100 else len(found)}"
        return TestResult(
            True, f"Conexão estabelecida. {amount} mensagens com falha nas últimas 24 h."
        )

    async def collect(
        self, secret: Secret, config: Mapping[str, Any], checkpoint: Checkpoint | None
    ) -> AsyncIterator[Batch]:
        top = int(config.get("page_size", 200))
        start = self.clock() - timedelta(hours=int(config.get("backfill_hours", 24)))
        after = None
        if checkpoint and checkpoint.get("log_end"):
            after = (odata_date(checkpoint["log_end"]), str(checkpoint["message_guid"]))
        async with self.client() as client:
            while True:
                found = await self.logs(
                    client, secret, config, self.query(config, after, start, top)
                )
                if not found:
                    return
                last = found[-1]
                after = (odata_date(last["LogEnd"]), str(last["MessageGuid"]))
                yield Batch(
                    [to_event(log) for log in found],
                    {"log_end": after[0].isoformat(), "message_guid": after[1]},
                )
                if len(found) < top:
                    return
