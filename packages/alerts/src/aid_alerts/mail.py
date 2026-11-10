"""E-mail transacional por SMTP: `smtp://` com STARTTLS quando há usuário, `smtps://` direto.
Usado pelos avisos de Cota (#31) e pelos alertas (#41)."""

import os
import smtplib
import ssl
from collections.abc import Sequence
from email.message import EmailMessage
from typing import Protocol
from urllib.parse import unquote, urlsplit

FROM_ADDRESS = "Integration AI Doctor <nao-responda@jayv.dev>"


class Mailer(Protocol):
    def send(self, to: Sequence[str], subject: str, body: str) -> None: ...


class SmtpMailer:
    def __init__(self, smtp_url: str, sender: str = FROM_ADDRESS) -> None:
        self.url = urlsplit(smtp_url)
        self.sender = sender

    def send(self, to: Sequence[str], subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self.sender
        message["To"] = ", ".join(to)
        message["Subject"] = subject
        message.set_content(body)
        host, port = self.url.hostname or "", self.url.port or 0
        context = ssl.create_default_context()
        if self.url.scheme == "smtps":
            with smtplib.SMTP_SSL(host, port, timeout=10, context=context) as smtp:
                self.login(smtp)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=10) as smtp:
                if self.url.username:
                    smtp.starttls(context=context)
                self.login(smtp)
                smtp.send_message(message)

    def login(self, smtp: smtplib.SMTP) -> None:
        if self.url.username:
            smtp.login(unquote(self.url.username), unquote(self.url.password or ""))


def mailer_from_env() -> SmtpMailer:
    return SmtpMailer(os.environ["SMTP_URL"], os.environ.get("MAIL_FROM", FROM_ADDRESS))
