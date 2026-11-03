"""Leitura dos documentos no bucket doctor-knowledge com a chave de serviço (job de plataforma)."""

from urllib.parse import quote

import httpx

BUCKET = "doctor-knowledge"


class KnowledgeStore:
    def __init__(self, url: str, service_key: str) -> None:
        self.base = f"{url.rstrip('/')}/storage/v1/object/{BUCKET}"
        self.headers = {"apikey": service_key, "authorization": f"Bearer {service_key}"}

    async def read(self, path: str) -> bytes | None:
        """`None` se o arquivo não existe (upload que não terminou ou já apagado)."""
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            response = await client.get(f"{self.base}/{quote(path)}", headers=self.headers)
        if response.status_code in (400, 404):
            return None
        # Rede ou 5xx: sobe, e o Pub/Sub reentrega a mensagem.
        response.raise_for_status()
        return response.content
