"""Leitura do Log bruto no Storage com a chave de serviço: o worker é job de plataforma."""

from urllib.parse import quote

import httpx

from aid_ingestion.pipeline import ObjectStore

BUCKET = "doctor-raw-logs"


class SupabaseObjectStore(ObjectStore):
    def __init__(self, url: str, service_key: str) -> None:
        self.base = f"{url.rstrip('/')}/storage/v1/object/{BUCKET}"
        self.headers = {"apikey": service_key, "authorization": f"Bearer {service_key}"}

    async def read(self, path: str) -> bytes | None:
        # Falha de rede ou 5xx sobe como exceção: o Pub/Sub reentrega a mensagem.
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            response = await client.get(f"{self.base}/{quote(path)}", headers=self.headers)
        if response.status_code in (400, 404):
            return None
        response.raise_for_status()
        return response.content
