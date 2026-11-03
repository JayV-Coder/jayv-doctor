# Retenção e LGPD

| Rota | Quem | Efeito |
|---|---|---|
| `GET /api/v1/privacy` | Todo Papel | Retenção efetiva por classe (com padrão e limites), envio ao LLM, provedor de IA e exclusão agendada |
| `PUT /api/v1/privacy/retention` | Owner ou Admin com MFA | `{ data_class, days }` dentro dos limites → `204` |
| `PUT /api/v1/privacy/llm` | Owner ou Admin com MFA | `{ enabled }` → `204` |
| `POST /api/v1/privacy/deletion` | Owner com MFA | `{ confirmation: "<slug>" }` → `202`, exclusão em 7 dias |
| `DELETE /api/v1/privacy/deletion` | Owner com MFA | Cancela a exclusão agendada → `204` |
| `POST /api/v1/privacy/subject/search` | Owner ou Admin com MFA | `{ reference }` → `{ events, first_seen, last_seen }` |
| `POST /api/v1/privacy/subject/erase` | Owner ou Admin com MFA | `{ reference }` → `{ events_erased }` |

- **Classes e limites** (os limites por plano chegam com o #31): Logs brutos 30 dias (7 a 90), Eventos 90 (30 a 365), Incidentes e Diagnósticos 180 (90 a 730), auditoria 365 (365 a 1.825). A Base de conhecimento fica até o cliente excluir.
- **Job diário** (`aid-retention`, 03:00 BRT, worker de diagnóstico): Logs brutos vencidos saem do Storage e depois do banco (o `expires_at` de cada Log bruto aceito segue a retenção da Organização, e mudar a política recalcula os existentes); cada Organização tem Incidentes resolvidos, Eventos, Execuções e auditoria vencidos apagados (Incidente aberto e Execução ligada a Incidente que fica não saem); partições inteiras que nenhuma Organização precisa saem com `drop`; cada execução grava `retention.purge` com as contagens. Organizações suspensas também passam pela purga. Uma Organização que falhe não impede as outras (o job devolve `failures`). **Desvio do ticket:** Cloud Scheduler em vez de `pg_cron`, que é do jayv-coder no projeto compartilhado (ADR-0009).
- **Envio ao LLM desligado:** o Diagnóstico roda como rules_only, com a nota; a indexação da Base grava os Fragmentos sem embedding, e a busca vai só pelo texto. Nenhuma chamada ao provedor.
- **Exclusão total:** depois da carência, o job congela a Organização (`status = 'deleted'`: token de ingestão e API param de aceitar escrita), apaga os arquivos das pastas da Organização nos dois buckets, os segredos dos Conectores no Vault e todo o schema `doctor` da Organização (cascade), e grava o comprovante em `deletion_receipts` (contagens e ids dos Conectores, para a verificação). `public.organizations` é do jayv-coder e não é tocada. Verificação: `SUPABASE_DB_URL=... uv run python scripts/verify_tenant_deleted.py <tenant_id>`.
- **Titular:** a Referência vai no corpo e vira HMAC com a chave da Organização. Apagar tira os Eventos e a Referência das chaves de correlação das Execuções e das fusões; a Trilha de auditoria guarda só a quantidade apagada (`subject.erased`).
