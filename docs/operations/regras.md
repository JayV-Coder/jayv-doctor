# Regras e abertura de Incidentes

Etapa 3 do motor (ADR-0003): Regras determinísticas, em código Python puro (`packages/diagnosis-engine`), classificam o sintoma de uma Execução fechada. Elas **não atribuem responsabilidade**.

## Versões

O pacote tem versão de calendário (`rules@2026.10.1`). Cada versão de cada Regra está em `doctor.rule_definitions`, um catálogo global e só de leitura, semeado pela migração. Regra nova ou alterada ganha versão nova (migração + `RULESET_VERSION`). O match guarda `rule_code` e `rule_version`, e a FK impede apagar uma versão que já gerou match: o match antigo continua rastreável. O teste do worker confere que o catálogo do banco é o do código.

## Catálogo `2026.10.1`

| Código | Dispara quando | Categoria | Dica de severidade |
|---|---|---|---|
| INT-001 | `error.http_status` 401/403 ou `error.category = AUTH` | AUTH | alta |
| INT-002 | 429 ou `RATE_LIMIT` | RATE_LIMIT | média |
| INT-003 | 504, `TIMEOUT` ou "timeout" na mensagem | TIMEOUT | alta |
| INT-004 | 400/422 ou `VALIDATION` | VALIDATION | média |
| INT-005 | `BUSINESS_REJECTION`, BAPIRET2 tipo E/A ou `error.code` V1/VL | BUSINESS_REJECTION | alta |
| INT-006 | 409, `DUPLICATE` ou "duplicate"/"já existe" | DUPLICATE | baixa |
| INT-007 | envio sem confirmação depois de 5 min | PENDING_CONFIRMATION | média |
| INT-008 | contagem ou status de origem e destino diferentes | DIVERGENCE | alta |

INT-001 a INT-006 só olham Eventos com `error`: texto num Evento INFO não abre Incidente.

Convenções de `attributes` lidas pelas Regras (os Conectores e a ingestão preenchem):

- **INT-005:** `bapiret2` ou `bapi_return`, lista ou item no formato BAPIRET2 (`type`, `id`, `number`, `message`).
- **INT-007:** `confirmation = "pending"` no envio e `"received"` ou `"confirmed"` na resposta. Dispara se o último envio não tem confirmação depois dele e a Execução fechou 5 min ou mais depois dele.
- **INT-008:** `reconciliation` com `source_count`/`target_count` e/ou `source_status`/`target_status`.

## Incidentes

O worker `diagnosis` consome `rules.evaluate` (posto pelo fechamento da Execução), grava os matches e escolhe o match principal: o de maior dica de severidade, e no empate o primeiro do catálogo. A Execução entra num Incidente só:

- o aberto (`open` ou `investigating`) da mesma Integração e categoria cuja janela de ocorrências, alargada em 30 min para cada lado, cruza a da Execução;
- senão, um novo, com título "Categoria · Integração" e a Regra/versão que o abriu.

Sem Incidente aberto na janela, um `resolved` há até 24 h com a mesma Integração e categoria é reaberto (histórico `reopened`) em vez de nascer outro (ticket #20).

Severidade: a dica da Regra, um nível acima em produção, e crítica a partir de 20 Execuções. Ela só sobe automaticamente. Abrir põe `incident.opened` na outbox; somar Execução, `incident.updated`. Quem consome esses tópicos chega com o Diagnóstico (#24) e os alertas (v0.3); até lá o worker só confirma a entrega.

Um lock por Integração e categoria evita dois Incidentes abertos para a mesma assinatura. Mensagem repetida não duplica (unique do match por versão e da Execução no Incidente). Execução fundida em outra não é avaliada: a sobrevivente é, quando fecha.
