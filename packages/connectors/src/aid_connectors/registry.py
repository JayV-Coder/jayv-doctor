"""Conectores disponíveis, por `provider`. A API (validação e teste de conexão) e o worker
(Sincronização) usam o mesmo registro."""

from aid_connectors.base import Connector
from aid_connectors.fake import FakeConnector
from aid_connectors.gcp.connector import GcpLoggingConnector

REGISTRY: dict[str, type[Connector]] = {"fake": FakeConnector, "gcp": GcpLoggingConnector}
