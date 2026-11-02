import smtplib
import ssl
from typing import Any

import pytest
from aid_api.auth import Claims, get_claims
from aid_api.errors import ApiError
from aid_api.mailer import Mailer, SmtpMailer, get_mailer
from aid_api.main import create_app
from aid_api.members import (
    Deliver,
    Invitation,
    Member,
    MemberRepository,
    get_member_repository,
    last_owner,
)
from aid_api.permissions import (
    GOVERN,
    IMPORT_LOGS,
    MANAGE_CONNECTORS,
    MANAGE_MEMBERS,
    OPERATE,
    VIEW,
)
from fastapi.testclient import TestClient

USER_ID = "00000000-0000-4000-8000-0000000a0001"
TENANT_ID = "00000000-0000-4000-8000-00000000ac01"
TARGET_ID = "00000000-0000-4000-8000-0000000000f1"
ROLES = ["owner", "admin", "analyst", "viewer"]


class FakeRepository(MemberRepository):
    def __init__(self, error: ApiError | None = None) -> None:
        self.error = error
        self.token_hashes: list[str] = []

    def fail(self) -> None:
        if self.error:
            raise self.error

    async def members(self, claims: Claims) -> list[Member]:
        self.fail()
        return []

    async def invitations(self, claims: Claims) -> list[Invitation]:
        self.fail()
        return []

    async def invite(
        self, claims: Claims, email: str, role: str, token_hash: str
    ) -> tuple[str, str]:
        self.fail()
        self.token_hashes.append(token_hash)
        return TARGET_ID, "Acme"

    async def resend(self, claims: Claims, target: str, token_hash: str, deliver: Deliver) -> None:
        self.fail()
        await deliver("carla@acme.test", "Acme")
        self.token_hashes.append(token_hash)

    async def revoke(self, claims: Claims, target: str) -> None:
        self.fail()

    async def accept(self, claims: Claims, token_hash: str) -> str:
        self.fail()
        self.token_hashes.append(token_hash)
        return TENANT_ID

    async def update_role(self, claims: Claims, target: str, role: str) -> None:
        self.fail()

    async def remove(self, claims: Claims, target: str) -> None:
        self.fail()


class FakeMailer(Mailer):
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    def send_invitation(self, email: str, organization: str, url: str) -> None:
        self.sent.append((email, organization, url))


def claims(role: str | None, aal: str = "aal2") -> Claims:
    return Claims(
        sub=USER_ID,
        email="ana@acme.test",
        aal=aal,
        tenant_id=TENANT_ID if role else None,
        tenant_role=role,
    )


def client(
    identity: Claims,
    repository: FakeRepository | None = None,
    mailer: FakeMailer | None = None,
) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_claims] = lambda: identity
    app.dependency_overrides[get_member_repository] = lambda: repository or FakeRepository()
    app.dependency_overrides[get_mailer] = lambda: mailer or FakeMailer()
    return TestClient(app)


INVITE = {"email": "carla@acme.test", "role": "analyst"}
MANAGER_ENDPOINTS: list[tuple[str, str, dict[str, Any] | None]] = [
    ("GET", "/api/v1/memberships", None),
    ("PATCH", f"/api/v1/memberships/{TARGET_ID}", {"role": "viewer"}),
    ("DELETE", f"/api/v1/memberships/{TARGET_ID}", None),
    ("GET", "/api/v1/invitations", None),
    ("POST", "/api/v1/invitations", INVITE),
    ("POST", f"/api/v1/invitations/{TARGET_ID}/resend", None),
    ("DELETE", f"/api/v1/invitations/{TARGET_ID}", None),
]


# A matriz do ticket #6, escrita aqui por extenso: é a fonte independente do código.
@pytest.mark.parametrize(
    ("roles", "allowed"),
    [
        (VIEW, ["owner", "admin", "analyst", "viewer"]),
        (OPERATE, ["owner", "admin", "analyst"]),
        (IMPORT_LOGS, ["owner", "admin", "analyst"]),
        (MANAGE_CONNECTORS, ["owner", "admin"]),
        (MANAGE_MEMBERS, ["owner", "admin"]),
        (GOVERN, ["owner"]),
    ],
)
def test_matriz_de_permissoes(roles: tuple[str, ...], allowed: list[str]) -> None:
    assert sorted(roles) == sorted(allowed)


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize(("method", "path", "body"), MANAGER_ENDPOINTS)
def test_so_owner_e_admin_gerenciam(
    role: str, method: str, path: str, body: dict[str, Any] | None
) -> None:
    response = client(claims(role)).request(method, path, json=body)
    if role in ("owner", "admin"):
        assert response.status_code < 300
    else:
        assert response.status_code == 403
        assert response.json()["code"] == "forbidden"


@pytest.mark.parametrize(("method", "path", "body"), MANAGER_ENDPOINTS)
def test_gestao_exige_mfa(method: str, path: str, body: dict[str, Any] | None) -> None:
    response = client(claims("owner", aal="aal1")).request(method, path, json=body)
    assert response.status_code == 403
    assert response.json()["code"] == "mfa_required"


@pytest.mark.parametrize(("method", "path", "body"), MANAGER_ENDPOINTS)
def test_sem_organizacao_ativa_responde_no_active_tenant(
    method: str, path: str, body: dict[str, Any] | None
) -> None:
    response = client(claims(None)).request(method, path, json=body)
    assert response.status_code == 403
    assert response.json()["code"] == "no_active_tenant"


def test_convite_guarda_so_o_hash_e_envia_o_token_no_fragmento() -> None:
    repository = FakeRepository()
    mailer = FakeMailer()
    response = client(claims("owner"), repository, mailer).post("/api/v1/invitations", json=INVITE)

    assert response.status_code == 201
    assert response.json() == {"id": TARGET_ID}
    email, organization, url = mailer.sent[0]
    assert (email, organization) == ("carla@acme.test", "Acme")
    prefix, token = url.split("#")
    assert prefix.endswith("/convites/aceitar")
    assert len(repository.token_hashes[0]) == 64
    assert token not in repository.token_hashes[0]


def test_falha_no_email_nao_perde_o_convite() -> None:
    class BrokenMailer(FakeMailer):
        def send_invitation(self, email: str, organization: str, url: str) -> None:
            raise OSError

    response = client(claims("owner"), mailer=BrokenMailer()).post(
        "/api/v1/invitations", json=INVITE
    )
    assert response.status_code == 503
    assert response.json()["code"] == "mail_unavailable"


def test_reenvio_com_falha_no_email_mantem_o_link_antigo() -> None:
    class BrokenMailer(FakeMailer):
        def send_invitation(self, email: str, organization: str, url: str) -> None:
            raise OSError

    repository = FakeRepository()
    response = client(claims("owner"), repository, BrokenMailer()).post(
        f"/api/v1/invitations/{TARGET_ID}/resend"
    )
    assert response.status_code == 503
    assert repository.token_hashes == []


def test_smtp_verifica_o_certificado(monkeypatch: pytest.MonkeyPatch) -> None:
    contexts: list[ssl.SSLContext] = []

    class FakeSmtp:
        def __init__(self, *_: Any, context: ssl.SSLContext, **__: Any) -> None:
            contexts.append(context)

        def __enter__(self) -> "FakeSmtp":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def login(self, user: str, password: str) -> None:
            return None

        def send_message(self, message: object) -> None:
            return None

    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSmtp)
    SmtpMailer("smtps://u:p@mail.test:465", "a@b.test").send_invitation("c@d.test", "Acme", "url")
    assert contexts[0].verify_mode == ssl.CERT_REQUIRED
    assert contexts[0].check_hostname


def test_smtp_com_senha_nao_trafega_sem_tls(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class FakeSmtp:
        def __init__(self, *_: Any, **__: Any) -> None:
            return None

        def __enter__(self) -> "FakeSmtp":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def starttls(self, context: ssl.SSLContext) -> None:
            calls.append("starttls")

        def login(self, user: str, password: str) -> None:
            calls.append("login")

        def send_message(self, message: object) -> None:
            return None

    monkeypatch.setattr(smtplib, "SMTP", FakeSmtp)
    SmtpMailer("smtp://u:p@mail.test:587", "a@b.test").send_invitation("c@d.test", "Acme", "url")
    assert calls == ["starttls", "login"]


def test_aceite_leva_o_token_no_corpo_e_nao_exige_organizacao_ativa() -> None:
    repository = FakeRepository()
    response = client(claims(None, aal="aal1"), repository).post(
        "/api/v1/invitations/accept", json={"token": "abc"}
    )
    assert response.status_code == 200
    assert response.json() == {"tenant_id": TENANT_ID}
    assert len(repository.token_hashes[0]) == 64


def test_payload_nao_define_tenant() -> None:
    response = client(claims("owner")).post(
        "/api/v1/invitations", json={**INVITE, "tenant_id": TENANT_ID}
    )
    assert response.status_code == 422


def test_ultimo_owner_responde_409() -> None:
    response = client(claims("owner"), FakeRepository(last_owner())).patch(
        f"/api/v1/memberships/{TARGET_ID}", json={"role": "admin"}
    )
    assert response.status_code == 409
    assert response.json()["code"] == "last_owner"


@pytest.mark.parametrize(
    ("sqlstate", "status", "code"),
    [
        ("DR001", 409, "last_owner"),
        ("DR002", 410, "invitation_gone"),
        ("DR003", 403, "invitation_email_mismatch"),
        ("DR004", 409, "already_member"),
        ("23505", 409, "already_invited"),
        ("42501", 403, "forbidden"),
        ("P0002", 404, "not_found"),
    ],
)
def test_erros_do_banco_viram_codigos_da_api(sqlstate: str, status: int, code: str) -> None:
    from aid_api.members import translate

    error = translate(sqlstate)
    assert error is not None
    assert (error.status, error.code) == (status, code)
