"""Critério do #42: a assinatura é verificável com os exemplos da documentação. Os blocos de
código de docs/api/webhooks.md rodam aqui contra a assinatura de verdade (`aid_alerts.signing`)."""

import json
import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from aid_alerts.signing import new_secret, sign

DOC = Path(__file__).resolve().parents[3] / "docs" / "api" / "webhooks.md"
BODY = json.dumps({"version": "webhook.v1", "event": "incident.opened", "título": "ação"}).encode()


def block(language: str) -> str:
    found = re.search(rf"```{language}\n(.*?)```", DOC.read_text(encoding="utf-8"), re.S)
    assert found, f"bloco {language} na documentação"
    return found.group(1)


def python_verify() -> Callable[..., bool]:
    scope: dict[str, Any] = {}
    exec(block("python"), scope)  # noqa: S102 - o código é o da nossa documentação
    return scope["verify"]  # type: ignore[no-any-return]


def test_exemplo_python_confere_a_assinatura() -> None:
    verify = python_verify()
    secret = new_secret()
    header = sign(secret, BODY)
    assert verify(secret, header, BODY)
    assert not verify(secret, header, BODY + b"x")
    assert not verify("whsec_outro", header, BODY)
    assert not verify(secret, sign(secret, BODY, now=1_000_000_000), BODY)


@pytest.mark.skipif(shutil.which("node") is None, reason="sem Node")
def test_exemplo_node_confere_a_assinatura() -> None:
    secret = new_secret()
    cases = {
        "ok": sign(secret, BODY),
        "old": sign(secret, BODY, now=1_000_000_000),
    }
    script = block("js") + (
        "\nconst [secret, ok, old, body] = process.argv.slice(1);"
        "\nconst raw = Buffer.from(body, 'base64');"
        "\nconsole.log(JSON.stringify([verify(secret, ok, raw), verify(secret, ok,"
        " Buffer.concat([raw, Buffer.from('x')])), verify('whsec_outro', ok, raw),"
        " verify(secret, old, raw)]));"
    )
    import base64

    result = subprocess.run(  # noqa: S603 - Node local com o script do teste
        [
            shutil.which("node") or "node",
            "-e",
            script,
            secret,
            cases["ok"],
            cases["old"],
            base64.b64encode(BODY).decode(),
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    assert json.loads(result.stdout) == [True, False, False, False]
