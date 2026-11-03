# aid-diagnosis-engine

Motor de diagnóstico, parte determinística (ADR-0003): Regras versionadas (`rules`) e severidade e
título de Incidentes (`incidents`). Sem banco nem rede: o worker `diagnosis` carrega a Execução,
chama `rules.evaluate` e grava. Catálogo e convenções em `docs/operations/regras.md`.
