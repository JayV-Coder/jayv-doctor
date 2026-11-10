"""Conectores disponíveis, por `provider`. A API (validação e teste de conexão) e o worker
(Sincronização) usam o mesmo registro."""

from aid_connectors.base import Connector
from aid_connectors.fake import FakeConnector
from aid_connectors.gcp.connector import GcpLoggingConnector
from aid_connectors.odata.connector import ODataConnector
from aid_connectors.salesforce.connector import SalesforceConnector
from aid_connectors.sap.integration_suite import SapIntegrationSuiteConnector

REGISTRY: dict[str, type[Connector]] = {
    "fake": FakeConnector,
    "gcp": GcpLoggingConnector,
    "odata": ODataConnector,
    "salesforce": SalesforceConnector,
    "sap": SapIntegrationSuiteConnector,
}
