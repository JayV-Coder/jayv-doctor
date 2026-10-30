import json
from types import TracebackType
from typing import Any, Self, cast

import pytest
from aid_api.auth import Claims
from aid_api.db import tenant_tx
from sqlalchemy.ext.asyncio import AsyncEngine


class FakeConnection:
    def __init__(self) -> None:
        self.statements: list[tuple[str, dict[str, Any] | None]] = []

    async def execute(self, statement: Any, parameters: dict[str, Any] | None = None) -> None:
        self.statements.append((str(statement), parameters))


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

    role, jwt_claims = engine.connection.statements
    assert role[0] == "set local role authenticated"
    assert "set_config('request.jwt.claims'" in jwt_claims[0]
    assert jwt_claims[1] is not None
    assert json.loads(jwt_claims[1]["claims"]) == {"sub": "u1"}
