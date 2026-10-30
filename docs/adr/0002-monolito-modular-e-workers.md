# Monólito modular para a API e workers assíncronos separados

A API é um único serviço FastAPI organizado em módulos (`orgs`, `connectors`, `ingestion`, `incidents`, `diagnosis`, `knowledge`, `audit`). Ingestão, correlação e diagnóstico rodam como workers separados no Cloud Run, acionados por Pub/Sub. Isso reduz a operação inicial sem impedir a extração de serviços quando o volume justificar. Os módulos só conversam pelas interfaces públicas de `packages/*`, nunca por imports internos cruzados.
