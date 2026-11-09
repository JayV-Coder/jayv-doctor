"""Agente local (ticket #39): fila offline sem duplicar, assinatura, revogação, atualização
assinada, Sanitização local e nenhuma porta de entrada."""

import ast
import base64
import hashlib
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from aid_agent import main as agent_main
from aid_agent.buffer import Buffer
from aid_agent.client import Platform, PlatformError
from aid_agent.collectors import DirectoryCollector, RfcFunctionCollector, RfcTableCollector
from aid_agent.identity import Credentials, load_key, signature_headers
from aid_agent.updater import apply, signed_payload
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

INTEGRATION = "00000000-0000-4000-8000-0000000001a1"
SM58 = "Data;Hora;Função;Destino;Status;Texto\n{rows}"


class FakePlatform:
    """A API como o agente a vê: deduplica pelo `event_id` (como a ingestão) e pode cair."""

    def __init__(self) -> None:
        self.online = True
        self.revoked = False
        self.received: dict[str, dict[str, Any]] = {}
        self.posts = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        if not self.online:
            raise httpx.ConnectError("sem rede")
        assert request.headers["x-aid-signature"]
        if self.revoked:
            return httpx.Response(401, json={"code": "invalid_agent"})
        if request.url.path == "/api/v1/agent/config":
            # A query vai assinada junto com o caminho.
            assert request.url.query
            return httpx.Response(304)
        if request.url.path == "/api/v1/agent/events":
            if len(request.content) > 1_000_000:
                return httpx.Response(413)
            self.posts += 1
            events = json.loads(request.content)["events"]
            for event in events:
                self.received.setdefault(event["event_id"], event)
            return httpx.Response(202, json={"accepted": len(events), "rejected": []})
        return httpx.Response(204)


def platform_for(fake: FakePlatform, tmp_path: Path) -> Platform:
    credentials = Credentials("https://api.test", "a-1", "aid_agt_x")
    return Platform(
        credentials, Ed25519PrivateKey.generate(), transport=httpx.MockTransport(fake.handler)
    )


def export(folder: Path, name: str, count: int, start: int = 0) -> None:
    rows = "\n".join(
        f"2026-11-0{1 + (i // 1000)};10:{(i // 60) % 60:02d}:{i % 60:02d};Z_ORDERS;ECCPRD;erro;"
        f"Pedido {4500000000 + i} recusado, contato ana@cliente.com.br"
        for i in range(start, start + count)
    )
    (folder / name).write_text(SM58.format(rows=rows), encoding="utf-8")


def test_offline_por_horas_envia_o_buffer_sem_duplicar(tmp_path: Path) -> None:
    folder = tmp_path / "exports"
    folder.mkdir()
    fake = FakePlatform()
    platform = platform_for(fake, tmp_path)
    buffer = Buffer(tmp_path / "buffer.sqlite3")
    config = {
        "collections": [
            {"type": "directory", "path": str(folder), "pattern": "*.csv", "format": "csv"}
        ]
    }

    # 2 h offline: 24 rodadas de 5 min, cada uma com exportação nova e a anterior regravada.
    fake.online = False
    for round_ in range(24):
        export(folder, f"sm58-{round_:02d}.csv", 30, start=round_ * 30)
        export(folder, f"sm58-{max(round_ - 1, 0):02d}.csv", 30, start=max(round_ - 1, 0) * 30)
        agent_main.cycle(platform, buffer, config, INTEGRATION)
    assert fake.received == {}
    assert buffer.size() == 24 * 30

    # A rede volta; a primeira resposta se perde depois de gravada (reenvio idempotente).
    fake.online = True
    agent_main.cycle(platform, buffer, config, INTEGRATION)
    agent_main.cycle(platform, buffer, config, INTEGRATION)
    assert len(fake.received) == 24 * 30
    assert buffer.size() == 0


def test_resposta_perdida_reenvia_o_mesmo_event_id(tmp_path: Path) -> None:
    fake = FakePlatform()
    lost = {"once": True}

    def flaky(request: httpx.Request) -> httpx.Response:
        response = fake.handler(request)
        if lost["once"]:
            lost["once"] = False
            raise httpx.ReadTimeout("resposta perdida")
        return response

    credentials = Credentials("https://api.test", "a-1", "aid_agt_x")
    platform = Platform(
        credentials, Ed25519PrivateKey.generate(), transport=httpx.MockTransport(flaky)
    )
    buffer = Buffer(tmp_path / "b.sqlite3")
    folder = tmp_path / "exports"
    folder.mkdir()
    export(folder, "sm58.csv", 10)
    config = {"collections": [{"type": "directory", "path": str(folder)}]}
    agent_main.cycle(platform, buffer, config, INTEGRATION)
    assert buffer.size() == 10  # gravado na plataforma, mas sem confirmação no agente
    agent_main.cycle(platform, buffer, config, INTEGRATION)
    assert (len(fake.received), fake.posts, buffer.size()) == (10, 2, 0)


def test_sanitiza_localmente_antes_de_enfileirar(tmp_path: Path) -> None:
    folder = tmp_path / "exports"
    folder.mkdir()
    export(folder, "sm58.csv", 1)
    buffer = Buffer(tmp_path / "b.sqlite3")
    DirectoryCollector({"path": str(folder)}, INTEGRATION, buffer).collect()
    stored = json.dumps(buffer.take(10))
    assert "ana@cliente.com.br" not in stored


def test_revogado_para_na_proxima_chamada(tmp_path: Path) -> None:
    fake = FakePlatform()
    platform = platform_for(fake, tmp_path)
    assert platform.config(0, "0.1.0") is None
    fake.revoked = True
    with pytest.raises(PlatformError):
        platform.config(0, "0.1.0")


class FakeRfc:
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call(self, function: str, **parameters: Any) -> dict[str, Any]:
        self.calls.append((function, parameters))
        return self.result


def test_rfc_le_so_a_tabela_e_os_campos_autorizados(tmp_path: Path) -> None:
    rfc = FakeRfc(
        {
            "DATA": [
                {
                    "WA": "0000000000123456|20261101|101500|000003|51|E0|E0|101|"
                    "Material 4711 não existe"
                },
                {
                    "WA": "0000000000123457|20261101|101600|000001|53||||"
                    "Aplicação documento contabilizado"
                },
            ]
        }
    )
    buffer = Buffer(tmp_path / "b.sqlite3")
    fields = [
        "DOCNUM",
        "LOGDAT",
        "LOGTIM",
        "COUNTR",
        "STATUS",
        "STAMQU",
        "STAMID",
        "STAMNO",
        "STATXT",
    ]
    added = RfcTableCollector(
        {"table": "EDIDS", "fields": fields}, INTEGRATION, buffer, lambda: rfc
    ).collect()
    assert added == 2
    function, parameters = rfc.calls[0]
    assert (function, parameters["QUERY_TABLE"]) == ("RFC_READ_TABLE", "EDIDS")
    assert [line["TEXT"].split(" '")[0] for line in parameters["OPTIONS"]] == [
        "LOGDAT >",
        "OR ( LOGDAT =",
        "AND LOGTIM >=",
    ]
    events = {event["execution_id"]: event for event in buffer.take(10)}
    assert events["0000000000123456"]["error"]["code"] == "IDOC 51"
    assert "error" not in events["0000000000123457"]
    # Lido de novo (mesmo Checkpoint de data), não duplica.
    assert (
        RfcTableCollector(
            {"table": "EDIDS", "fields": fields}, INTEGRATION, buffer, lambda: rfc
        ).collect()
        == 0
    )


def test_funcao_customizada_slg1(tmp_path: Path) -> None:
    rfc = FakeRfc(
        {
            "ET_MESSAGES": [
                {
                    "TIMESTAMP": "20261101101500",
                    "TYPE": "E",
                    "ID": "M3",
                    "NUMBER": "305",
                    "MESSAGE": "Material bloqueado",
                    "OBJECT": "MM",
                    "EXTERNAL_ID": "4500012345",
                },
            ]
        }
    )
    buffer = Buffer(tmp_path / "b.sqlite3")
    RfcFunctionCollector({"name": "Z_AID_READ_SLG1"}, INTEGRATION, buffer, lambda: rfc).collect()
    [event] = buffer.take(10)
    assert (event["severity"], event["error"]["code"]) == ("ERROR", "M3 305")
    assert rfc.calls[0][0] == "Z_AID_READ_SLG1"


def manifest_for(
    key: Ed25519PrivateKey, data: bytes, url: str = "https://releases.test/aid-agent.pyz"
) -> dict[str, Any]:
    found = {"version": "0.2.0", "url": url, "sha256": hashlib.sha256(data).hexdigest()}
    found["signature"] = base64.b64encode(key.sign(signed_payload(found))).decode()
    return found


def release_public(key: Ed25519PrivateKey) -> str:
    raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode()


def test_atualizacao_so_com_assinatura_e_sha256_validos(tmp_path: Path) -> None:
    release, attacker = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    target = tmp_path / "aid-agent.pyz"
    target.write_bytes(b"v1")
    good = manifest_for(release, b"v2")
    assert not apply(
        manifest_for(attacker, b"evil"), target, lambda _: b"evil", release_public(release)
    )
    assert not apply(good, target, lambda _: b"outro conteudo", release_public(release))
    assert not apply(
        manifest_for(release, b"v2", "http://releases.test/a.pyz"),
        target,
        lambda _: b"v2",
        release_public(release),
    )
    assert not apply(good, target, lambda _: b"v2", None)
    assert target.read_bytes() == b"v1"
    assert apply(good, target, lambda _: b"v2", release_public(release))
    assert target.read_bytes() == b"v2"


def test_assinatura_bate_com_a_da_api(tmp_path: Path) -> None:
    from aid_api.ingestion.agent import verify

    key = Ed25519PrivateKey.generate()
    raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    headers = signature_headers(
        key, "aid_agt_x", "POST", "/api/v1/agent/events", b"{}", 1_800_000_000
    )
    verify(
        base64.b64encode(raw).decode(),
        "POST",
        "/api/v1/agent/events",
        headers["x-aid-timestamp"],
        headers["x-aid-signature"],
        b"{}",
        1_800_000_000,
    )


def test_nenhuma_porta_de_entrada() -> None:
    """Critério do ticket: o agente não escuta. Nenhum módulo usa bind, listen ou servidor."""
    forbidden = {
        "bind",
        "listen",
        "serve_forever",
        "start_server",
        "HTTPServer",
        "TCPServer",
        "create_server",
        "uvicorn",
    }
    source = Path(agent_main.__file__).parent
    for file in source.glob("*.py"):
        tree = ast.parse(file.read_text(encoding="utf-8"))
        names = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        names |= {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        names |= {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import | ast.ImportFrom)
            for alias in node.names
        }
        assert not names & forbidden, (file.name, names & forbidden)


def test_registro_novo_troca_a_chave_e_token_errado_preserva_a_atual(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AID_AGENT_STATE", str(tmp_path))
    answers = iter([{"agent_id": "a-1", "secret": "aid_agt_1", "certificate": None}])

    def fake_register(_api: str, token: str, key: str, _version: str) -> dict[str, Any]:
        if token == "errado":  # noqa: S105 - token de teste
            raise PlatformError("token de registro inválido ou vencido")
        return (
            next(answers)
            if token == "primeiro"  # noqa: S105 - token de teste
            else {"agent_id": "a-1", "secret": "aid_agt_2", "certificate": None}
        )

    monkeypatch.setattr(agent_main, "register", fake_register)
    api = ["--api", "https://api.test"]
    assert agent_main.main(["register", *api, "--token", "primeiro"]) == 0
    first = (tmp_path / "agent.key").read_bytes()
    assert oct((tmp_path / "agent.key").stat().st_mode & 0o777) == "0o600"
    with pytest.raises(PlatformError):
        agent_main.main(["register", *api, "--token", "errado"])
    assert (tmp_path / "agent.key").read_bytes() == first
    # Rotação: o mesmo volume, chave nova.
    assert agent_main.main(["register", *api, "--token", "segundo"]) == 0
    assert (tmp_path / "agent.key").read_bytes() != first
    assert load_key(tmp_path) is not None


def test_lote_acima_de_1_mb_e_dividido_e_recusa_nao_trava_a_fila(tmp_path: Path) -> None:
    fake = FakePlatform()
    platform = platform_for(fake, tmp_path)
    buffer = Buffer(tmp_path / "b.sqlite3")
    big = [
        {
            "event_id": f"0192e1c4-7b2c-7d4e-8f00-{n:012d}",
            "integration_id": INTEGRATION,
            "error": {"message": "x" * 8000},
        }
        for n in range(500)
    ]
    buffer.enqueue(big)
    assert agent_main.flush(platform, buffer) == 500
    assert (len(fake.received), buffer.size()) == (500, 0)
    assert max(len(json.dumps(batch)) for batch in agent_main.batches(big)) < 1_000_000

    def refuse(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"code": "validation_error"})

    credentials = Credentials("https://api.test", "a-1", "aid_agt_x")
    refusing = Platform(
        credentials, Ed25519PrivateKey.generate(), transport=httpx.MockTransport(refuse)
    )
    buffer.enqueue(
        [{"event_id": "0192e1c4-7b2c-7d4e-8f00-999999999999", "integration_id": INTEGRATION}]
    )
    assert agent_main.flush(refusing, buffer) == 0
    assert (buffer.size(), buffer.rejected()) == (0, 1)


def test_arquivo_regravado_e_lido_inteiro_sem_reenviar_o_que_ja_foi(tmp_path: Path) -> None:
    folder = tmp_path / "exports"
    folder.mkdir()
    buffer = Buffer(tmp_path / "b.sqlite3")
    collector = DirectoryCollector({"path": str(folder)}, INTEGRATION, buffer)
    export(folder, "sm58.csv", 100)
    assert collector.collect() == 100
    buffer.ack([event["event_id"] for event in buffer.take(500)])
    # Regravado no lugar com outro conteúdo, maior: tudo é novo.
    export(folder, "sm58.csv", 150, start=1000)
    assert collector.collect() == 150
    buffer.ack([event["event_id"] for event in buffer.take(500)])
    # Regravado com os mesmos 150 e mais 10 no fim: só os 10.
    export(folder, "sm58.csv", 160, start=1000)
    assert collector.collect() == 10


class PagedRfc:
    """RFC_READ_TABLE com ROWSKIPS sobre um conjunto fixo de linhas."""

    def __init__(self, rows: list[str]) -> None:
        self.rows = rows
        self.calls = 0

    def call(self, function: str, **parameters: Any) -> dict[str, Any]:
        self.calls += 1
        start = parameters["ROWSKIPS"]
        page = self.rows[start : start + parameters["ROWCOUNT"]]
        return {"DATA": [{"WA": row} for row in page]}


def test_rfc_pagina_e_continua_do_cursor_sem_perder_linhas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aid_agent import collectors

    monkeypatch.setattr(collectors, "MAX_PAGES", 2)
    rows = [
        f"{n:016d}|20261101|10{n // 60 % 60:02d}{n % 60:02d}|000001|51|E0|E0|101|Erro {n}"
        for n in range(3000)
    ]
    rfc = PagedRfc(rows)
    buffer = Buffer(tmp_path / "b.sqlite3")
    fields = [
        "DOCNUM",
        "LOGDAT",
        "LOGTIM",
        "COUNTR",
        "STATUS",
        "STAMQU",
        "STAMID",
        "STAMNO",
        "STATXT",
    ]
    spec = {"table": "EDIDS", "fields": fields, "max_rows": 1000}
    buffer.save_checkpoint("rfc_table:EDIDS", json.dumps({"since": "20261101000000"}))
    collector = RfcTableCollector(spec, INTEGRATION, buffer, lambda: rfc)
    assert collector.collect() == 2000
    assert json.loads(buffer.checkpoint("rfc_table:EDIDS") or "{}")["skip"] == 2000
    assert collector.collect() == 1000
    assert buffer.size() == 3000
    cursor = json.loads(buffer.checkpoint("rfc_table:EDIDS") or "{}")
    assert cursor == {"since": "20261101104959", "skip": 0}
