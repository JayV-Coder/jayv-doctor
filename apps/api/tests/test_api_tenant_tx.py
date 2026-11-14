import json
from types import TracebackType
from typing import Any, Self, cast

import pytest
from aid_api.core.auth import Claims
from aid_api.core.db import tenant_tx
from sqlalchemy.ext.asyncio import AsyncEngine


class FakeConnection:
    def __init__(self) -> None:
        self.statements: list[tuple[str, dict[str, Any] | None]] = []

    async def execute(self, statement: Any, parameters: dict[str, Any] | None = None) -> None:
        self.statements.append((str(statement), parameters))

    async def scalar(self, statement: Any, parameters: dict[str, Any] | None = None) -> bool:
        # A conferência do Vínculo (#48): aqui ele existe.
        self.statements.append((str(statement), parameters))
        return True


class FakeBegin:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> FakeConnection:
        return self.connection

    async def __aexit__(
        self, kind: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        return None


class FakeEngine:
    def __init__(self) -> None:
        self.connection = FakeConnection()

    def begin(self) -> FakeBegin:
        return FakeBegin(self.connection)

    def __call__(self) -> Self:
        return self


@pytest.mark.asyncio
async def test_tenant_tx_assume_authenticated_com_as_claims_do_jwt() -> None:
    engine = FakeEngine()
    claims = Claims(
        sub="u1", email=None, aal="aal1", tenant_id="t1", tenant_role="viewer", raw={"sub": "u1"}
    )
    async with tenant_tx(claims, cast("AsyncEngine", engine)):
        pass

    role, jwt_claims, membership = engine.connection.statements
    assert role[0] == "set local role authenticated"
    assert "doctor.memberships" in membership[0]
    assert "set_config('request.jwt.claims'" in jwt_claims[0]
    assert jwt_claims[1] is not None
    assert json.loads(jwt_claims[1]["claims"]) == {"sub": "u1"}


class RevokedConnection(FakeConnection):
    async def scalar(self, statement: Any, parameters: dict[str, Any] | None = None) -> bool:
        self.statements.append((str(statement), parameters))
        return False


@pytest.mark.asyncio
async def test_tenant_tx_recusa_quem_perdeu_o_vinculo_com_o_token_ainda_valido() -> None:
    from aid_api.core.errors import ApiError

    engine = FakeEngine()
    engine.connection = RevokedConnection()
    claims = Claims(
        sub="u1", email=None, aal="aal1", tenant_id="t1", tenant_role="viewer", raw={"sub": "u1"}
    )
    with pytest.raises(ApiError) as revoked:
        async with tenant_tx(claims, cast("AsyncEngine", engine)):
            pass
    assert (revoked.value.status, revoked.value.code) == (401, "membership_revoked")


@pytest.mark.asyncio
async def test_tenant_tx_sem_organizacao_nao_confere_vinculo() -> None:
    engine = FakeEngine()
    engine.connection = RevokedConnection()
    claims = Claims(
        sub="u1", email=None, aal="aal1", tenant_id=None, tenant_role=None, raw={"sub": "u1"}
    )
    async with tenant_tx(claims, cast("AsyncEngine", engine)):
        pass
    assert len(engine.connection.statements) == 2
