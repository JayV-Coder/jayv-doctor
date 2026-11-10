"""Conector Salesforce (ticket #37): objetos de log de integração do cliente, `ApexLog` e
`EventLogFile` (com Event Monitoring), por SOQL da allowlist e Checkpoint por
(SystemModstamp, Id) em cada fonte. Lê o `Sforce-Limit-Info` de toda resposta e para ao chegar a
80% do limite diário de API, até a janela seguinte."""

import asyncio
import logging
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from typing import Any, ClassVar
from urllib.parse import quote

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
from aid_connectors.salesforce.auth import Session, session
from aid_connectors.salesforce.mapping import moment, to_event
from aid_connectors.salesforce.soql import (
    APEX_LOG,
    EVENT_LOG_FILE,
    IDENTIFIER,
    OPERATORS,
    Filter,
    QueryNotAllowedError,
    Source,
    integration_log,
    literal,
    select,
)

log = logging.getLogger(__name__)
SOURCES = ("integration_log", "apex_log", "event_log_file")
LABELS = {
    "integration_log": "objeto de log de integração",
    "apex_log": "ApexLog",
    "event_log_file": "EventLogFile",
}
API_VERSION = re.compile(r"^[4-9][0-9]\.0$")
USAGE = re.compile(r"api-usage=(\d+)/(\d+)")
DAILY_SHARE = 0.8
# O limite diário é uma janela móvel de 24 h: a Sincronização volta a conferir de hora em hora.
LIMIT_WINDOW_SECONDS = 3600


class SourceUnavailableError(Exception):
    """A fonte não existe nesta org (INVALID_TYPE) ou o usuário não lê o objeto
    (INSUFFICIENT_ACCESS): ela fica de fora e as outras seguem."""


def error_codes(response: httpx.Response) -> set[str]:
    try:
        body = response.json()
    except ValueError:
        return set()
    items = body if isinstance(body, list) else [body]
    return {str(item.get("errorCode")) for item in items if isinstance(item, dict)}


def usage(response: httpx.Response) -> tuple[int, int] | None:
    found = USAGE.search(response.headers.get("sforce-limit-info", ""))
    return (int(found[1]), int(found[2])) if found else None


class SalesforceConnector:
    provider: ClassVar[str] = "salesforce"
    rate_limit: ClassVar[RateLimitPolicy] = RateLimitPolicy(requests_per_minute=60)

    def __init__(
        self,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.transport = transport
        self.sleep = sleep
        self.session: Session | None = None
        self.last_request: float | None = None

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=self.transport, timeout=httpx.Timeout(30.0))

    def validate_config(self, config: Mapping[str, Any]) -> ConfigErrors:
        errors: ConfigErrors = {}
        if config.get("environment", "production") not in ("production", "sandbox"):
            errors["environment"] = "production ou sandbox"
        if config.get("auth", "jwt_bearer") not in ("jwt_bearer", "web_server"):
            errors["auth"] = "jwt_bearer ou web_server"
        sources = config.get("sources")
        if not isinstance(sources, list) or not sources or not set(sources) <= set(SOURCES):
            errors["sources"] = "uma ou mais de " + ", ".join(SOURCES)
        if isinstance(sources, list) and "integration_log" in sources:
            try:
                self.integration_source(config)
            except QueryNotAllowedError as exc:
                errors["integration_log"] = str(exc)
        if not API_VERSION.match(str(config.get("api_version", "62.0"))):
            errors["api_version"] = "versão da API, como 62.0"
        page = config.get("page_size", 200)
        if not isinstance(page, int) or not 1 <= page <= 2000:
            errors["page_size"] = "de 1 a 2000"
        rpm = config.get("requests_per_minute", 60)
        if not isinstance(rpm, int) or not 1 <= rpm <= 600:
            errors["requests_per_minute"] = "de 1 a 600"
        return errors

    def integration_source(self, config: Mapping[str, Any]) -> Source:
        log = config.get("integration_log") or {}
        if not isinstance(log, Mapping):
            raise QueryNotAllowedError("configuração do objeto de log")
        mapped = [
            str(log[key])
            for key in (
                "operation_field",
                "severity_field",
                "message_field",
                "status_code_field",
                "execution_field",
            )
            if log.get(key)
        ]
        fields = [
            *[str(f) for f in log.get("fields", [])],
            *mapped,
            str(log.get("timestamp_field", "CreatedDate")),
        ]
        source = integration_log(
            str(log.get("object", "")), fields, str(log.get("timestamp_field", "CreatedDate"))
        )
        for item in self.filters(config):
            if item.field not in source.fields:
                raise QueryNotAllowedError(f"filtro fora dos campos: {item.field}")
        return source

    def filters(self, config: Mapping[str, Any]) -> list[Filter]:
        raw = (config.get("integration_log") or {}).get("filters", [])
        if not isinstance(raw, list) or len(raw) > 10:
            raise QueryNotAllowedError("até 10 filtros")
        found = []
        for item in raw:
            if not isinstance(item, Mapping) or not IDENTIFIER.match(str(item.get("field", ""))):
                raise QueryNotAllowedError("filtro inválido")
            operator = str(item.get("operator", "="))
            if operator not in OPERATORS:
                raise QueryNotAllowedError(f"operador fora da allowlist: {operator}")
            value = str(item.get("value", ""))
            # Mesma regra da consulta: valor recusado aqui não chega à Sincronização.
            literal(value)
            found.append(Filter(str(item["field"]), operator, value))
        return found

    def sources(self, config: Mapping[str, Any]) -> dict[str, Source]:
        """A allowlist desta config: só as fontes escolhidas, com os campos fixos ou os da
        config do objeto de log."""
        chosen: dict[str, Source] = {}
        for name in config.get("sources", []):
            if name == "integration_log":
                chosen[name] = self.integration_source(config)
            elif name == "apex_log":
                chosen[name] = APEX_LOG
            elif name == "event_log_file":
                chosen[name] = EVENT_LOG_FILE
        return chosen

    async def pace(self, config: Mapping[str, Any]) -> None:
        interval = 60.0 / int(config.get("requests_per_minute", 60))
        if self.last_request is not None:
            wait = interval - (time.monotonic() - self.last_request)
            if wait > 0:
                await self.sleep(round(wait, 1))
        self.last_request = time.monotonic()

    async def call(
        self, client: httpx.AsyncClient, secret: Secret, config: Mapping[str, Any], path: str
    ) -> Mapping[str, Any]:
        if self.session is None or self.session.expires_at < time.monotonic() + 60:
            self.session = await session(client, secret, config)
        await self.pace(config)
        version = str(config.get("api_version", "62.0"))
        try:
            response = await client.get(
                f"{self.session.instance_url}/services/data/v{version}{path}",
                headers={"authorization": f"Bearer {self.session.token}"},
            )
        except httpx.HTTPError as exc:
            raise ConnectorError("transient", "O Salesforce não respondeu.") from exc
        used = usage(response)
        if used and used[1] and used[0] / used[1] >= DAILY_SHARE:
            raise ConnectorError(
                "api_limit",
                f"Limite diário da API do Salesforce em {used[0] * 100 // used[1]}%: as"
                " Sincronizações pausam até a janela seguinte.",
                LIMIT_WINDOW_SECONDS,
            )
        if response.status_code == 200:
            try:
                body = response.json()
            except ValueError as exc:
                raise ConnectorError("transient", "Resposta inesperada do Salesforce.") from exc
            return body if isinstance(body, dict) else {}
        if response.status_code == 401:
            self.session = None
            raise ConnectorError("auth", "O Salesforce recusou a sessão.")
        codes = error_codes(response)
        if "REQUEST_LIMIT_EXCEEDED" in codes:
            raise ConnectorError(
                "api_limit",
                "Limite diário da API do Salesforce esgotado: as Sincronizações pausam até"
                " a janela seguinte.",
                LIMIT_WINDOW_SECONDS,
            )
        if codes & {"INVALID_TYPE", "INSUFFICIENT_ACCESS"} or response.status_code == 403:
            raise SourceUnavailableError(", ".join(sorted(codes)) or "403")
        if codes & {"INVALID_FIELD", "MALFORMED_QUERY", "INVALID_QUERY_FILTER_OPERATOR"}:
            # Campo da config que não existe no objeto: repetir não resolve.
            raise ConnectorError(
                "invalid",
                f"O Salesforce recusou a consulta ({', '.join(sorted(codes))}): confira os"
                " campos do objeto de log.",
            )
        raise ConnectorError("transient", f"O Salesforce respondeu HTTP {response.status_code}.")

    async def available(
        self, client: httpx.AsyncClient, secret: Secret, config: Mapping[str, Any]
    ) -> dict[str, bool]:
        """Quais fontes a org oferece, pela lista de objetos (`describeGlobal`)."""
        described = await self.call(client, secret, config, "/sobjects")
        # Nome de objeto no Salesforce não diferencia maiúsculas.
        names = {
            str(item.get("name")).lower()
            for item in described.get("sobjects", [])
            if isinstance(item, Mapping)
        }
        log = (config.get("integration_log") or {}).get("object")
        return {
            "integration_log": bool(log) and str(log).lower() in names,
            "apex_log": "apexlog" in names,
            "event_log_file": "eventlogfile" in names,
        }

    async def test_connection(
        self, secret: Secret, config: Mapping[str, Any], *, preview: bool = False
    ) -> TestResult:
        try:
            async with self.client() as client:
                capabilities = await self.available(client, secret, config)
        except ConnectorError as exc:
            return TestResult(False, exc.message)
        chosen = [name for name in config.get("sources", []) if name in SOURCES]
        missing = [name for name in chosen if not capabilities.get(name)]
        notes = [
            f"{LABELS[name]} indisponível nesta edição"
            if name != "integration_log"
            else "objeto de log de integração não encontrado nesta org"
            for name in missing
        ]
        working = [name for name in chosen if capabilities.get(name)]
        if not working:
            return TestResult(
                False,
                "Nenhuma das fontes escolhidas está disponível: " + "; ".join(notes) + ".",
                capabilities,
            )
        message = "Conexão estabelecida. Fontes: " + ", ".join(LABELS[n] for n in working) + "."
        if notes:
            joined = "; ".join(notes)
            message += f" {joined[0].upper()}{joined[1:]}."
        return TestResult(True, message, capabilities)

    async def collect(
        self, secret: Secret, config: Mapping[str, Any], checkpoint: Checkpoint | None
    ) -> AsyncIterator[Batch]:
        allowlist = self.sources(config)
        objects = {source.object: source for source in allowlist.values()}
        state: dict[str, Any] = dict((checkpoint or {}).get("sources", {}))
        page_size = int(config.get("page_size", 200))
        filters = self.filters(config)
        async with self.client() as client:
            for name, source in allowlist.items():
                try:
                    async for batch in self.pages(
                        client, secret, config, name, source, objects, state, page_size, filters
                    ):
                        yield batch
                except SourceUnavailableError as exc:
                    # Fonte que a edição não tem, ou que o usuário não lê: fica de fora e as
                    # outras seguem (#37). Sem o describeGlobal a cada Sincronização.
                    log.warning("Salesforce: fonte %s indisponível (%s)", name, exc)

    async def pages(
        self,
        client: httpx.AsyncClient,
        secret: Secret,
        config: Mapping[str, Any],
        name: str,
        source: Source,
        objects: Mapping[str, Source],
        state: dict[str, Any],
        page_size: int,
        filters: list[Filter],
    ) -> AsyncIterator[Batch]:
        while True:
            mark = state.get(name)
            after = (moment(mark["at"]), str(mark["id"])) if mark else None
            query = select(
                source,
                objects,
                after=after,
                limit=page_size,
                filters=filters if name == "integration_log" else (),
            )
            found = await self.call(client, secret, config, f"/query?q={quote(query)}")
            records = [r for r in found.get("records", []) if isinstance(r, Mapping)]
            if not records:
                break
            last = records[-1]
            state[name] = {
                "at": moment(last["SystemModstamp"]).isoformat(),
                "id": str(last["Id"]),
            }
            yield Batch(
                [to_event(record, source, config) for record in records],
                {"sources": {**state}},
            )
            if len(records) < page_size:
                break
