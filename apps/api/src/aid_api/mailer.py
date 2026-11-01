"""Envio de e-mail da aplicação. O Supabase Auth só cuida dos e-mails de login."""

import os
import smtplib
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
        secure = self.smtp_url.scheme == "smtps"
        client = smtplib.SMTP_SSL if secure else smtplib.SMTP
        with client(self.smtp_url.hostname or "", self.smtp_url.port or 0, timeout=10) as smtp:
            if self.smtp_url.username:
                smtp.login(unquote(self.smtp_url.username), unquote(self.smtp_url.password or ""))
            smtp.send_message(message)


def get_mailer() -> Mailer:
    return SmtpMailer(os.environ["SMTP_URL"], os.environ.get("MAIL_FROM", FROM_ADDRESS))
