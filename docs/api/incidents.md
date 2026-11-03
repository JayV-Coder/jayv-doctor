# Incidentes

Exigem `Authorization: Bearer <JWT do Supabase Auth>` e Organização ativa. Todo Papel lê; Analyst ou acima muda status, severidade e responsável e comenta (o banco confere o Papel na tabela).

| Rota | Efeito |
|---|---|
| `POST /api/v1/incidents/search` | Lista paginada (20 por página, última ocorrência primeiro) e contagem por status |
| `GET /api/v1/incidents/{id}` | Resumo, Execuções vinculadas, Regras como Evidência determinística e histórico |
| `PATCH /api/v1/incidents/{id}` | `status`, `severity`, `assignee_id` e `resolution_note` |
| `GET /api/v1/incidents/{id}/comments` | Comentários em ordem |
| `POST /api/v1/incidents/{id}/comments` | `{ body_md, mentions: [user_id] }` → `201` |

## Busca

Filtros no corpo, como em Execuções: `q`, `status[]`, `severity[]`, `category`, `integration_id`, `environment`, `assignee_id`, `from`, `to`, `cursor`, `limit`. `q` aceita o número (`INC-0142` ou `142`), ou `execution_id`, `trace_id` e nº do pedido das Execuções do Incidente (o pedido vira HMAC no servidor). `counts` traz a contagem por status com os outros filtros aplicados, para os chips da Tela 5.

## Status

`open → investigating → resolved | dismissed`, com reabertura (`resolved`/`dismissed` → `open`). O banco valida a transição (trigger) e cada mudança vai para `incident_history`. Resolver exige `resolution_note`, que alimenta a Base de conhecimento no #26.

Incidente `resolved` há até 24 h volta a `open` quando chega uma Execução com a mesma assinatura (Integração e categoria), em vez de abrir outro; o histórico registra `reopened` sem autor (foi a plataforma).

## Comentários

Menções a quem não é membro da Organização são descartadas sem erro; o texto fica.

## Erros (`application/problem+json`)

| Status | `code` | Quando |
|---|---|---|
| 403 | `forbidden` | Viewer mudando ou comentando |
| 404 | `not_found` | Incidente inexistente nesta Organização |
| 409 | `invalid_transition` | Transição de status não permitida |
| 422 | `invalid_assignee`, `validation_error`, `invalid_cursor` | Responsável de fora, resolver sem nota, filtros inválidos |
