"""Webhooks (#42): URL segura no cadastro e na conexão, e a assinatura."""

import asyncio
from collections.abc import Sequence

import httpcore
import pytest
from aid_alerts.network import PublicOnlyBackend, UnsafeUrlError, check_url
from aid_alerts.signing import new_secret, sign, verify


def resolving(*addresses: str):  # type: ignore[no-untyped-def]
    async def resolver(_: str) -> Sequence[str]:
        return addresses

    return resolver


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254",
        "https://169.254.169.254/latest/meta-data",
        "http://hooks.acme.com.br/aid",
        "https://10.0.0.5/hook",
        "https://127.0.0.1/hook",
        "https://[::1]/hook",
        "https://[fd00::1]/hook",
        "https://metadata.google.internal/computeMetadata/v1/",
        "https://localhost/hook",
        "https://servico.internal/hook",
        "https://user:senha@hooks.acme.com.br/aid",
    ],
)
def test_cadastro_recusa_endereco_inseguro(url: str) -> None:
    with pytest.raises(UnsafeUrlError):
        asyncio.run(check_url(url, resolving("200.160.2.3")))


def test_nome_que_resolve_para_rede_interna_e_recusado() -> None:
    with pytest.raises(UnsafeUrlError):
        asyncio.run(
            check_url("https://hooks.acme.com.br/aid", resolving("200.160.2.3", "10.1.2.3"))
        )
    asyncio.run(check_url("https://hooks.acme.com.br/aid", resolving("200.160.2.3")))


def test_conexao_so_vai_para_o_endereco_conferido() -> None:
    backend = PublicOnlyBackend(resolving("169.254.169.254"))
    with pytest.raises(httpcore.ConnectError):
        asyncio.run(backend.connect_tcp("hooks.acme.com.br", 443))
    with pytest.raises(httpcore.ConnectError):
        asyncio.run(PublicOnlyBackend().connect_tcp("10.0.0.5", 443))


def test_assinatura_confere_e_recusa_corpo_alterado_ou_vencido() -> None:
    secret = new_secret()
    body = b'{"version":"webhook.v1"}'
    header = sign(secret, body, now=1_800_000_000)
    assert header.startswith("t=1800000000,v1=")
    assert verify(secret, header, body, now=1_800_000_100)
    assert not verify(secret, header, body + b" ", now=1_800_000_100)
    assert not verify("whsec_outro", header, body, now=1_800_000_100)
    assert not verify(secret, header, body, now=1_800_000_301)
    assert not verify(secret, "v1=abc", body)
