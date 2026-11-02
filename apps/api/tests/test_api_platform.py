import time
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import pytest
from aid_api.core.auth import Claims, TokenVerifier, get_claims, get_verifier
from aid_api.core.idempotency import (
    IdempotencySession,
    IdempotencyStore,
    Stored,
    get_idempotency_store,
)
from aid_api.core.rate_limit import TokenBucketLimiter, get_limiter
from aid_api.core.telemetry import annotate_span
from aid_api.health.router import get_readiness
from aid_api.main import create_app
from aid_api.orgs.mailer import Mailer, get_mailer
from aid_api.orgs.repo import MemberRepository, get_member_repository, translate
from aid_api.orgs.schemas import Invitation
from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

USER_ID = "00000000-0000-4000-8000-0000000a0001"
TENANT_ID = "00000000-0000-4000-8000-00000000ac01"
OWNER = Claims(
    sub=USER_ID, email="ana@acme.test", aal="aal2", tenant_id=TENANT_ID, tenant_role="owner"
)
INVITE = {"email": "carla@acme.test", "role": "analyst"}


class MemorySession(IdempotencySession):
    """Como o Postgres: o que a requisição grava só vale se ela terminar sem erro."""

    def __init__(self, store: "MemoryStore", claims: Claims) -> None:
        self.store = store
        self.claims = claims
        self.pending: dict[str, dict[str, Any]] = {}

    async def reserve(self, key: str, request_hash: str) -> Stored | None:
        row = self.store.rows.get(key)
        if row is None:
            self.pending[key] = {"hash": request_hash, "status": None, "body": None}
            return None
        return Stored(row["hash"], row["status"], row["body"])

    async def remember(self, key: str, status: int, body: str) -> None:
        if self.store.fail_remember:
            raise OSError
        self.pending[key].update(status=status, body=body)


class MemoryStore(IdempotencyStore):
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}
        self.opened = 0
        self.fail_remember = False

    @asynccontextmanager
    async def session(self, claims: Claims) -> AsyncIterator[IdempotencySession]:
        self.opened += 1
        session = MemorySession(self, claims)
        yield session
        self.rows.update(session.pending)


class CountingRepository(MemberRepository):
    def __init__(self, fail: bool = False) -> None:
        self.invited = 0
        self.fail = fail

    async def invite(
        self, claims: Claims, email: str, role: str, token_hash: str
    ) -> tuple[str, str]:
        self.invited += 1
        if self.fail:
            error = translate("23505")
            assert error is not None
            raise error
        return f"id-{self.invited}", "Acme"

    async def invitations(self, claims: Claims) -> list[Invitation]:
        return []


class SilentMailer(Mailer):
    def send_invitation(self, email: str, organization: str, url: str) -> None:
        return None


@dataclass
class Harness:
    client: TestClient
    repository: CountingRepository
    store: MemoryStore


def harness(
    identity: Claims = OWNER,
    fail: bool = False,
    limiter: TokenBucketLimiter | None = None,
) -> Harness:
    repository = CountingRepository(fail)
    store = MemoryStore()
    app = create_app()
    app.dependency_overrides[get_claims] = lambda: identity
    app.dependency_overrides[get_member_repository] = lambda: repository
    app.dependency_overrides[get_mailer] = SilentMailer
    app.dependency_overrides[get_idempotency_store] = lambda: store
    app.dependency_overrides[get_limiter] = lambda: limiter or TokenBucketLimiter(1000, 1000)
    return Harness(TestClient(app, raise_server_exceptions=False), repository, store)


def invite(target: Harness, key: str = "k1", body: dict[str, str] = INVITE) -> Any:
    return target.client.post("/api/v1/invitations", json=body, headers={"Idempotency-Key": key})


def test_mesma_chave_e_mesmo_corpo_devolve_a_resposta_gravada_sem_novo_efeito() -> None:
    target = harness()
    first = invite(target)
    second = invite(target)
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json() == {"id": "id-1"}
    assert target.repository.invited == 1


def test_mesma_chave_com_corpo_diferente_responde_422() -> None:
    target = harness()
    invite(target)
    response = invite(target, body={**INVITE, "role": "viewer"})
    assert response.status_code == 422
    assert response.json()["code"] == "idempotency_key_reused"
    assert target.repository.invited == 1


def test_mesma_chave_de_outro_usuario_nao_reaproveita_a_resposta() -> None:
    target = harness()
    invite(target)
    target.client.app.dependency_overrides[get_claims] = lambda: Claims(  # type: ignore[attr-defined]
        sub="outro", email=None, aal="aal2", tenant_id=TENANT_ID, tenant_role="owner"
    )
    assert invite(target).status_code == 422


def test_erro_nao_grava_a_chave() -> None:
    target = harness(fail=True)
    assert invite(target).status_code == 409
    assert target.store.rows == {}


def test_falha_ao_gravar_a_resposta_desfaz_tudo_e_nao_prende_a_chave() -> None:
    target = harness()
    target.store.fail_remember = True
    assert invite(target).status_code == 500
    assert target.store.rows == {}
    target.store.fail_remember = False
    assert invite(target).status_code == 201


def test_resposta_gravada_nao_dispensa_a_permissao() -> None:
    target = harness()
    invite(target)
    target.client.app.dependency_overrides[get_claims] = lambda: Claims(  # type: ignore[attr-defined]
        sub=USER_ID, email=None, aal="aal2", tenant_id=TENANT_ID, tenant_role="viewer"
    )
    response = invite(target)
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"


def test_corpo_invalido_nao_reserva_a_chave() -> None:
    target = harness()
    response = invite(target, body={"email": "x"})
    assert response.status_code == 422
    assert target.store.opened == 0


def test_chave_vazia_responde_422() -> None:
    target = harness()
    response = invite(target, key="")
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_sem_chave_nada_e_gravado() -> None:
    target = harness()
    assert target.client.post("/api/v1/invitations", json=INVITE).status_code == 201
    assert target.store.rows == {}


def test_leitura_ignora_a_chave() -> None:
    target = harness()
    response = target.client.get("/api/v1/invitations", headers={"Idempotency-Key": "k"})
    assert response.status_code == 200
    assert target.store.rows == {}


def test_rate_limit_responde_429_com_retry_after() -> None:
    target = harness(limiter=TokenBucketLimiter(capacity=2, per_minute=60))
    statuses = [target.client.get("/api/v1/invitations").status_code for _ in range(3)]
    assert statuses == [200, 200, 429]
    response = target.client.get("/api/v1/invitations")
    assert response.json()["code"] == "rate_limited"
    assert int(response.headers["retry-after"]) >= 1
    assert response.headers["content-type"].startswith("application/problem+json")


def test_rate_limit_resiste_a_rajada_concorrente() -> None:
    limiter = TokenBucketLimiter(capacity=5, per_minute=60, clock=lambda: 0.0)
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda _: limiter.allow("k"), range(200)))
    assert sum(1 for wait in results if wait == 0) == 5


def test_rate_limit_separa_tenant_e_usuario() -> None:
    limiter = TokenBucketLimiter(capacity=1, per_minute=60)
    assert limiter.allow("a:1") == 0
    assert limiter.allow("a:2") == 0
    assert limiter.allow("a:1") > 0


def test_token_bucket_repoe_com_o_tempo() -> None:
    now = [0.0]
    limiter = TokenBucketLimiter(capacity=1, per_minute=60, clock=lambda: now[0])
    assert limiter.allow("k") == 0
    assert limiter.allow("k") > 0
    now[0] = 1.1
    assert limiter.allow("k") == 0


def test_rate_limit_nao_guarda_chaves_sem_limite() -> None:
    limiter = TokenBucketLimiter(capacity=1, per_minute=60, max_keys=2, clock=time.monotonic)
    for key in ["a", "b", "c"]:
        limiter.allow(key)
    assert len(limiter.buckets) == 2


def test_validacao_responde_problem_json_em_portugues_sem_ecoar_a_entrada() -> None:
    response = harness().client.post(
        "/api/v1/invitations", json={"email": "senha-secreta", "role": "analyst"}
    )
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "validation_error"
    assert "senha-secreta" not in response.text


def test_erro_inesperado_responde_problem_json_sem_detalhes() -> None:
    class Broken(CountingRepository):
        async def invitations(self, claims: Claims) -> list[Invitation]:
            raise RuntimeError("segredo interno")

    target = harness()
    target.client.app.dependency_overrides[get_member_repository] = Broken  # type: ignore[attr-defined]
    response = target.client.get("/api/v1/invitations")
    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/problem+json")
    assert "segredo" not in response.text


def test_healthz_nao_depende_do_banco() -> None:
    app = create_app()

    async def broken() -> None:
        raise OSError

    app.dependency_overrides[get_readiness] = lambda: broken
    assert TestClient(app).get("/healthz").status_code == 200


def test_readyz_testa_o_banco() -> None:
    app = create_app()

    async def healthy() -> None:
        return None

    async def broken() -> None:
        raise OSError

    app.dependency_overrides[get_readiness] = lambda: healthy
    assert TestClient(app).get("/readyz").status_code == 200
    app.dependency_overrides[get_readiness] = lambda: broken
    response = TestClient(app).get("/readyz")
    assert response.status_code == 503
    assert response.json()["code"] == "not_ready"


def test_span_leva_o_tenant_e_nunca_o_email() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    with provider.get_tracer("teste").start_as_current_span("rota") as span:
        assert span is trace.get_current_span()
        annotate_span(OWNER.tenant_id)
    attributes = exporter.get_finished_spans()[0].attributes or {}
    assert attributes["tenant.id"] == TENANT_ID
    assert "ana@acme.test" not in {str(value) for value in attributes.values()}


def test_openapi_publica_em_api_v1() -> None:
    response = TestClient(create_app()).get("/api/v1/openapi.json")
    assert "/api/v1/invitations" in response.json()["paths"]


@pytest.mark.parametrize("path", ["/api/v1/me", "/api/v1/memberships"])
def test_sem_jwt_responde_401(path: str) -> None:
    app = create_app()
    app.dependency_overrides[get_verifier] = lambda: TokenVerifier("http://auth.test")
    assert TestClient(app).get(path).status_code == 401
