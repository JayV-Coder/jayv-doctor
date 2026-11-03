"""Publicação no Pub/Sub pela API REST: sem SDK, com o token da conta de serviço do Cloud Run, ou
sem autenticação no emulador (PUBSUB_EMULATOR_HOST)."""

import base64
import time
from collections.abc import Mapping, Sequence

import httpx

METADATA_ACCESS_URL = (
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"
)
TIMEOUT = httpx.Timeout(10.0)
# O Pub/Sub aceita até 1000 mensagens por chamada; o relay manda no máximo um lote (100).
Message = tuple[bytes, Mapping[str, str]]


class PublishError(RuntimeError):
    """`rejected=True`: o Pub/Sub recusou estas mensagens (tópico inexistente, pedido inválido), e
    elas contam uma tentativa. `False`: o problema é do relay ou do Pub/Sub (token, IAM, 429,
    5xx, rede); a rodada para sem gastar tentativa de ninguém."""

    def __init__(self, detail: str, *, rejected: bool) -> None:
        super().__init__(detail)
        self.rejected = rejected


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
            try:
                response = await client.get(
                    METADATA_ACCESS_URL, headers={"Metadata-Flavor": "Google"}
                )
                response.raise_for_status()
                body = response.json()
                self.token = (body["access_token"], time.monotonic() + float(body["expires_in"]))
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                raise PublishError(
                    "token da conta de serviço indisponível", rejected=False
                ) from exc
        return {"authorization": f"Bearer {self.token[0]}"}

    async def publish(
        self, client: httpx.AsyncClient, topic: str, messages: Sequence[Message]
    ) -> None:
        url = f"{self.base}/v1/projects/{self.project}/topics/{topic}:publish"
        body = {
            "messages": [
                {"data": base64.b64encode(data).decode(), "attributes": dict(attributes)}
                for data, attributes in messages
            ]
        }
        try:
            response = await client.post(url, json=body, headers=await self.headers(client))
        except httpx.HTTPError as exc:
            raise PublishError(f"{topic}: {type(exc).__name__}", rejected=False) from exc
        # 200 basta: o Pub/Sub aceitou. Não depende do corpo da resposta.
        if response.status_code == 200:
            return
        raise PublishError(
            f"{topic}: HTTP {response.status_code}", rejected=response.status_code in (400, 404)
        )
