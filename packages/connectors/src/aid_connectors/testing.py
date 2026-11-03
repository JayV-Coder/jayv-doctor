"""Suíte de contrato que todo Conector novo herda e passa (ticket #14):

class TestMeuConectorContract(ConnectorContractTests):
    def make_connector(self): ...
    def valid_config(self): ...
    def invalid_config(self): ...
    def secret(self): ...
"""

import asyncio
import json
from collections.abc import Mapping
from typing import Any

from aid_contracts.events import validate_event

from aid_connectors.base import Batch, Checkpoint, Connector, Secret

INTEGRATION = "00000000-0000-4000-8000-0000000001a1"


class ConnectorContractTests:
    def make_connector(self) -> Connector:
        raise NotImplementedError

    def valid_config(self) -> Mapping[str, Any]:
        raise NotImplementedError

    def invalid_config(self) -> Mapping[str, Any]:
        raise NotImplementedError

    def secret(self) -> str:
        raise NotImplementedError

    def collect(self, checkpoint: Checkpoint | None = None) -> list[Batch]:
        connector = self.make_connector()

        async def gather() -> list[Batch]:
            return [
                batch
                async for batch in connector.collect(
                    Secret(self.secret()), self.valid_config(), checkpoint
                )
            ]

        return asyncio.run(gather())

    def test_provedor_e_limite_definidos(self) -> None:
        connector = self.make_connector()
        assert connector.provider
        assert connector.rate_limit.requests_per_minute > 0

    def test_config_valida_sem_erros_e_invalida_com_motivo(self) -> None:
        connector = self.make_connector()
        assert connector.validate_config(self.valid_config()) == {}
        assert connector.validate_config(self.invalid_config())

    def test_teste_de_conexao_com_credencial_valida(self) -> None:
        connector = self.make_connector()
        result = asyncio.run(connector.test_connection(Secret(self.secret()), self.valid_config()))
        assert result.ok
        assert self.secret() not in result.message

    def test_eventos_cumprem_o_contrato_com_a_integracao(self) -> None:
        for batch in self.collect():
            for event in batch.events:
                validate_event({**event, "integration_id": INTEGRATION})
                assert "tenant_id" not in event

    def test_checkpoint_serializavel_e_sempre_avanca(self) -> None:
        previous: Checkpoint | None = None
        for batch in self.collect():
            json.dumps(batch.checkpoint)
            assert batch.checkpoint != previous
            previous = batch.checkpoint

    def test_retomar_do_checkpoint_nao_repete_eventos(self) -> None:
        batches = self.collect()
        assert batches, "a config válida precisa gerar ao menos um lote"
        first = batches[0]
        resumed = self.collect(first.checkpoint)
        seen = {event["event_id"] for event in first.events}
        assert not seen & {event["event_id"] for batch in resumed for event in batch.events}

    def test_event_id_estavel_entre_coletas(self) -> None:
        def ids() -> list[str]:
            return [event["event_id"] for batch in self.collect() for event in batch.events]

        assert ids() == ids()
