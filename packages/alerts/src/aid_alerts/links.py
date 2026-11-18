"""Endereços do app que a plataforma põe em alertas, webhooks, chamados, convites e relatórios.

O app do Doctor vive no `site` (JayV-Coder/site), em `/doctor`. `APP_URL` é a origem do site; sem
o idioma, o site manda para o da pessoa e mantém a query (o `#` fica com o navegador).
"""

import os

PREFIX = "/doctor"


def app_base() -> str:
    return os.environ.get("APP_URL", "http://127.0.0.1:3000").rstrip("/")


def app_link(path: str, base: str | None = None) -> str:
    """`path` dentro do app, começando com `/`: `/incidents/<id>`, `/connectors`…"""
    return f"{(base if base is not None else app_base()).rstrip('/')}{PREFIX}{path}"
