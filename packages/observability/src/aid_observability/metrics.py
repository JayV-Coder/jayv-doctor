"""Métricas da plataforma no Cloud Monitoring (`custom.googleapis.com/aid/<nome>`), gravadas
direto pela API REST a cada minuto: no Cloud Run a CPU fica parada fora das requisições, e um
exportador periódico perderia pontos."""

import time
from collections.abc import Mapping
from datetime import UTC, datetime

import httpx

METADATA_URL = (
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"
)
PREFIX = "custom.googleapis.com/aid/"
# Limite da API por chamada.
BATCH = 200


class MonitoringWriter:
    def __init__(self, project: str, client: httpx.AsyncClient) -> None:
        self.project = project
        self.client = client
        self.token: tuple[str, float] | None = None

    async def headers(self) -> dict[str, str]:
        if self.token is None or self.token[1] < time.monotonic() + 60:
            response = await self.client.get(METADATA_URL, headers={"metadata-flavor": "Google"})
            response.raise_for_status()
            body = response.json()
            self.token = (body["access_token"], time.monotonic() + float(body["expires_in"]))
        return {"authorization": f"Bearer {self.token[0]}"}

    async def gauges(self, values: Mapping[str, float]) -> int:
        """Grava um ponto por métrica (`global`, agora). Devolve quantas foram gravadas."""
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        series = [
            {
                "metric": {"type": f"{PREFIX}{name}"},
                "resource": {"type": "global", "labels": {"project_id": self.project}},
                "points": [{"interval": {"endTime": now}, "value": {"doubleValue": float(value)}}],
            }
            for name, value in sorted(values.items())
        ]
        for start in range(0, len(series), BATCH):
            response = await self.client.post(
                f"https://monitoring.googleapis.com/v3/projects/{self.project}/timeSeries",
                json={"timeSeries": series[start : start + BATCH]},
                headers=await self.headers(),
            )
            response.raise_for_status()
        return len(series)
