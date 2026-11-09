# Relatório técnico

Exportação em português de um Incidente e do seu Diagnóstico atual (o último que já terminou), para outra equipe. Gerar é assíncrono: o worker de diagnóstico monta o arquivo e o sobe no bucket privado `doctor-reports`, em `{tenant_id}/{report_id}.{pdf|md}`.

| Rota | Papel | O que faz |
|---|---|---|
| `POST /api/v1/incidents/{id}/reports` `{format: pdf\|md, include_timeline, include_event_excerpts}` | Analyst ou acima | `202 {report_id, status}`; idempotente com `Idempotency-Key` |
| `GET /api/v1/incidents/{id}/reports` | todo Papel | histórico (50 mais recentes) |
| `GET /api/v1/reports/{id}` | todo Papel | metadados, `download_url` assinada de 5 min quando `ready` e, para Analyst ou acima, os links |
| `POST /api/v1/reports/{id}/shares` | Analyst ou acima | `201 {id, url, expires_at}`: link de 7 dias; `409 report_not_ready` antes de pronto |
| `DELETE /api/v1/reports/{id}/shares/{share}` | Analyst ou acima | revoga na hora (`204`) |
| `POST /api/v1/shared-reports` `{token}` | sem sessão | o arquivo (`attachment`); `404` para link inválido, vencido ou revogado |

## Template

- **Cabeçalho:** Organização, Incidente (`INC-0142` e título), data, versão do Diagnóstico, versão das regras e modelo.
- **Seções:** Resumo; Causa provável com o rótulo **"confiança heurística"** (no Inconclusivo, a seção "Evidências insuficientes" com "O que coletar"); Hipóteses; Evidências com o id do registro (`[E1] Evento <uuid>`); Recomendações; Revisão humana (veredito, revisor, comentário, ou "Pendente"); Timeline (opcional, até 500 Eventos das Execuções do Incidente).
- **Rodapé:** data (horário de Brasília) e o **sha256 do corpo em Markdown**, igual no PDF e no `.md` e gravado em `reports.content_sha256`.
- **Sanitização:** os Eventos já chegam sanitizados da ingestão, e todo texto passa de novo pelo sanitizador. As Referências de negócio (`hmac:…`) viram `[referência]`. Os trechos de Evento (opcionais) trazem só operação, severidade, erro e atributos, sem Referência nem contexto de negócio.
- **PDF:** WeasyPrint a partir do HTML, com DejaVu Sans Mono. A imagem do worker instala Pango, HarfBuzz e a fonte (`SYSTEM_PACKAGES`).

## Link compartilhável

O token aparece uma vez, na `url` (`{APP_URL}/compartilhado#<token>`); o banco guarda só o sha256. A abertura conta o acesso e grava `report.share_accessed` na Trilha de auditoria (ADR-0014). Pedido, geração, compartilhamento e revogação também ficam na trilha (`report.requested`, `report.generated`, `report.shared`, `report.share_revoked`).

## Retenção

O Relatório segue o Incidente: quando a purga apaga o Incidente, a linha sai em cascata e o job diário remove o arquivo sem dono. Na exclusão total da Organização, o bucket entra com os outros, e o armazenamento conta na Cota `storage_bytes`.
