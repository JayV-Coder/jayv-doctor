"""Envio de e-mail da aplicação. O Supabase Auth só cuida dos e-mails de login."""

import os
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import unquote, urlsplit

FROM_ADDRESS = "Integration AI Doctor <nao-responda@jayv.dev>"


class Mailer:
    def send_invitation(self, email: str, organization: str, url: str) -> None:
        raise NotImplementedError


class SmtpMailer(Mailer):
    def __init__(self, smtp_url: str, sender: str) -> None:
        self.smtp_url = urlsplit(smtp_url)
        self.sender = sender

    def send_invitation(self, email: str, organization: str, url: str) -> None:
        message = EmailMessage()
        message["From"] = self.sender
        message["To"] = email
        message["Subject"] = "Você foi convidado para o Integration AI Doctor"
        message.set_content(
            f"Você foi convidado para a organização {organization} no Integration AI Doctor.\n\n"
            f"Para aceitar, abra o link abaixo. Ele vale por 7 dias.\n{url}\n\n"
            "Se você não esperava este convite, ignore este e-mail.\n"
        )
        host, port = self.smtp_url.hostname or "", self.smtp_url.port or 0
        # O contexto padrão do smtplib não confere certificado nem nome do servidor.
        context = ssl.create_default_context()
        if self.smtp_url.scheme == "smtps":
            with smtplib.SMTP_SSL(host, port, timeout=10, context=context) as smtp:
                self.authenticate(smtp)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=10) as smtp:
                # Sem usuário é o Mailpit local; com usuário, a senha não trafega em claro.
                if self.smtp_url.username:
                    smtp.starttls(context=context)
                self.authenticate(smtp)
                smtp.send_message(message)

    def authenticate(self, smtp: smtplib.SMTP) -> None:
        if self.smtp_url.username:
            smtp.login(unquote(self.smtp_url.username), unquote(self.smtp_url.password or ""))


def get_mailer() -> Mailer:
    return SmtpMailer(os.environ["SMTP_URL"], os.environ.get("MAIL_FROM", FROM_ADDRESS))
