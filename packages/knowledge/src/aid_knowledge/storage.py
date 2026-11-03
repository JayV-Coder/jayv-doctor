"""Leitura dos documentos no bucket doctor-knowledge com a chave de serviço (job de plataforma)."""

from urllib.parse import quote

import httpx

BUCKET = "doctor-knowledge"


def missing(response: httpx.Response) -> bool:
    """O Storage responde 400 com `error: "not_found"` para objeto inexistente; outro 400 (chave
    inválida, bucket inexistente, que também vem com `statusCode: "404"`) é configuração e não
    pode virar "arquivo sumiu"."""
    if response.status_code == 404:
        return True
    if response.status_code != 400:
        return False
    try:
        body = response.json()
    except ValueError:
        return False
    return bool(body.get("error") == "not_found" or body.get("message") == "Object not found")


class KnowledgeStore:
    def __init__(self, url: str, service_key: str) -> None:
        self.base = f"{url.rstrip('/')}/storage/v1/object/{BUCKET}"
        self.headers = {"apikey": service_key, "authorization": f"Bearer {service_key}"}

    async def read(self, path: str) -> bytes | None:
        """`None` se o arquivo não existe (upload que não terminou ou já apagado)."""
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            response = await client.get(f"{self.base}/{quote(path)}", headers=self.headers)
        if missing(response):
            return None
        # Rede, 5xx ou configuração errada: sobe, e o Pub/Sub reentrega a mensagem.
        response.raise_for_status()
        return response.content
