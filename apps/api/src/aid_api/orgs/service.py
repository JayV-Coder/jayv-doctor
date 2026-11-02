"""Regras dos Convites que não dependem do banco: token e envio."""

import asyncio
import hashlib
import os
import secrets

from aid_api.core.errors import ApiError
from aid_api.orgs.mailer import Mailer


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


# O token vai no fragmento, que o navegador não envia: fica fora dos logs do servidor web.
def invitation_url(token: str) -> str:
    base = os.environ.get("APP_URL", "http://127.0.0.1:3000")
    return f"{base}/convites/aceitar#{token}"


async def send_invitation(mailer: Mailer, email: str, organization: str, token: str) -> None:
    try:
        await asyncio.to_thread(mailer.send_invitation, email, organization, invitation_url(token))
    except OSError as exc:
        # O convite fica pendente e dá para reenviar pela tela.
        raise ApiError(503, "mail_unavailable", "Não foi possível enviar o e-mail.") from exc
