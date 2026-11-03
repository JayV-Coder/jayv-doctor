"""Supabase Storage com o JWT do próprio Usuário: as políticas do bucket valem, sem service_role."""

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import quote

import httpx

from aid_api.core.errors import ApiError

BUCKET = "doctor-raw-logs"
TIMEOUT = httpx.Timeout(10.0)


@dataclass
class Head:
    data: bytes
    size: int


def unavailable() -> ApiError:
    return ApiError(503, "storage_unavailable", "Armazenamento indisponível. Tente de novo.")


class Storage:
    async def sign_upload(self, token: str, path: str) -> str:
        """URL assinada para o navegador subir o arquivo direto no Storage."""
        raise NotImplementedError

    async def head(self, token: str, path: str, limit: int) -> Head | None:
        """Os primeiros `limit` bytes e o tamanho total, ou `None` se o objeto não existe."""
        raise NotImplementedError

    async def sign_download(self, token: str, path: str, seconds: int) -> str:
        """URL assinada de leitura, válida por `seconds`."""
        raise NotImplementedError


class SupabaseStorage(Storage):
    def __init__(self, url: str, key: str) -> None:
        self.base = f"{url.rstrip('/')}/storage/v1"
        self.key = key

    def headers(self, token: str) -> dict[str, str]:
        return {"authorization": f"Bearer {token}", "apikey": self.key}

    def object_path(self, path: str) -> str:
        return f"{BUCKET}/{quote(path)}"

    async def sign_upload(self, token: str, path: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.post(
                    f"{self.base}/object/upload/sign/{self.object_path(path)}",
                    headers=self.headers(token),
                )
        except httpx.HTTPError as exc:
            raise unavailable() from exc
        if response.status_code != 200:
            raise unavailable()
        return f"{self.base}{response.json()['url']}"

    async def sign_download(self, token: str, path: str, seconds: int) -> str:
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.post(
                    f"{self.base}/object/sign/{self.object_path(path)}",
                    headers=self.headers(token),
                    json={"expiresIn": seconds},
                )
        except httpx.HTTPError as exc:
            raise unavailable() from exc
        if response.status_code in (400, 403, 404):
            # Sem permissão no bucket ou objeto já apagado pela retenção.
            raise ApiError(404, "not_found", "Log bruto não encontrado.")
        if response.status_code != 200:
            raise unavailable()
        return f"{self.base}{response.json()['signedURL']}"

    async def head(self, token: str, path: str, limit: int) -> Head | None:
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.get(
                    f"{self.base}/object/authenticated/{self.object_path(path)}",
                    headers={**self.headers(token), "range": f"bytes=0-{limit - 1}"},
                )
        except httpx.HTTPError as exc:
            raise unavailable() from exc
        if response.status_code in (400, 404):
            return None
        # Range fora do arquivo: o objeto existe e está vazio.
        if response.status_code == 416:
            return Head(data=b"", size=0)
        if response.status_code not in (200, 206):
            raise unavailable()
        # 206 traz o total em "bytes 0-65535/12345"; 200 é o arquivo inteiro.
        total = re.search(r"/(\d+)$", response.headers.get("content-range", ""))
        size = int(total.group(1)) if total else len(response.content)
        return Head(data=response.content[:limit], size=size)


@lru_cache
def get_storage() -> Storage:
    return SupabaseStorage(os.environ["SUPABASE_URL"], os.environ["SUPABASE_PUBLISHABLE_KEY"])
