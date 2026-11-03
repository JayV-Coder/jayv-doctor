"""Publicação no Pub/Sub pela API REST: sem SDK, com o token da conta de serviço do Cloud Run, ou
sem autenticação no emulador (PUBSUB_EMULATOR_HOST)."""

import base64
import time
from collections.abc import Mapping

import httpx

METADATA_ACCESS_URL = (
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"
)
TIMEOUT = httpx.Timeout(10.0)


class PublishError(RuntimeError):
    """O Pub/Sub não aceitou a mensagem; ela fica na outbox para a próxima rodada."""


class PubSubPublisher:
    def __init__(self, project: str, *, emulator_host: str | None = None) -> None:
        self.project = project
        self.base = f"http://{emulator_host}" if emulator_host else "https://pubsub.googleapis.com"
        self.emulated = emulator_host is not None
        self.token: tuple[str, float] | None = None

    async def headers(self, client: httpx.AsyncClient) -> dict[str, str]:
        if self.emulated:
            return {}
        if self.token is None or self.token[1] < time.monotonic() + 60:
            response = await client.get(METADATA_ACCESS_URL, headers={"Metadata-Flavor": "Google"})
            response.raise_for_status()
            body = response.json()
            self.token = (body["access_token"], time.monotonic() + float(body["expires_in"]))
        return {"authorization": f"Bearer {self.token[0]}"}

    async def publish(self, topic: str, data: bytes, attributes: Mapping[str, str]) -> str:
        url = f"{self.base}/v1/projects/{self.project}/topics/{topic}:publish"
        message = {"data": base64.b64encode(data).decode(), "attributes": dict(attributes)}
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            try:
                response = await client.post(
                    url, json={"messages": [message]}, headers=await self.headers(client)
                )
            except httpx.HTTPError as exc:
                raise PublishError(topic) from exc
        if response.status_code != 200:
            raise PublishError(f"{topic}: HTTP {response.status_code}")
        return str(response.json()["messageIds"][0])
