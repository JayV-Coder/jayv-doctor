# Relatório técnico

Exportação em português de um Incidente e do seu Diagnóstico atual (o último que já terminou), para outra equipe. Gerar é assíncrono: o worker de diagnóstico monta o arquivo e o sobe no bucket privado `doctor-reports`, em `{tenant_id}/{report_id}.{pdf|md}`.

| Rota | Papel | O que faz |
|---|---|---|
| `POST /api/v1/incidents/{id}/reports` `{format: pdf\|md, include_timeline, include_event_excerpts}` | Analyst ou acima | `202 {report_id, status}`; idempotente com `Idempotency-Key` |
| `GET /api/v1/incidents/{id}/reports` | todo Papel | histórico (50 mais recentes), com os links ativos para Analyst ou acima |
| `GET /api/v1/reports/{id}` | todo Papel | metadados, `download_url` assinada de 5 min quando `ready` e, para Analyst ou acima, os links |
| `POST /api/v1/reports/{id}/shares` | Analyst ou acima | `201 {id, url, expires_at}`: link de 7 dias; `409 report_not_ready` antes de pronto |
| `DELETE /api/v1/reports/{id}/shares/{share}` | Analyst ou acima | revoga na hora (`204`) |
| `POST /api/v1/shared-reports` `{token}` | sem sessão | o arquivo (`attachment`); `404` para link inválido, vencido ou revogado |

## Template

- **Cabeçalho:** Organização, Incidente (`INC-0142` e título), data, versão do Diagnóstico, versão das regras e modelo.
- **Seções:** Resumo; Causa provável com o rótulo **"confiança heurística"** (no Inconclusivo, a seção "Evidências insuficientes" com "O que coletar"); Hipóteses; Evidências com o id do registro (`[E1] Evento <uuid>`); Recomendações; Revisão humana (veredito, nome do revisor, comentário, ou "Pendente"); Timeline opcional, com os 500 Eventos mais recentes das Execuções do Incidente (data e hora) e um aviso quando há mais.
- **Revisor:** sai o nome do perfil, nunca o e-mail, porque o relatório vai para fora da Organização. Sem nome, sai "Revisor da Organização".
- **Hashes:** `reports.content_sha256` (e a trilha `report.generated`) é o sha256 do **arquivo entregue**, que confere com `sha256sum`. O rodapé traz o **sha256 do texto** (o corpo em Markdown), igual no PDF e no `.md`.
- **Markdown:** o texto vindo de log e de Usuário é escapado (sem cabeçalho, link ou imagem injetados), e os trechos vão em bloco de código com cerca maior que qualquer sequência de crases do trecho.
- **Sanitização:** os Eventos já chegam sanitizados da ingestão, e todo texto passa de novo pelo sanitizador. As Referências de negócio (`hmac:…`) viram `[referência]`. Os trechos de Evento (opcionais) trazem só operação, severidade, erro e atributos, sem Referência nem contexto de negócio.
- **PDF:** WeasyPrint a partir do HTML, com DejaVu Sans Mono. A imagem do worker instala Pango, HarfBuzz e a fonte (`SYSTEM_PACKAGES`).

## Link compartilhável

O token aparece uma vez, na `url` (`{APP_URL}/compartilhado#<token>`); o banco guarda só o sha256. O link abre enquanto não vencer nem for revogado, com a Organização ativa (sem suspensão nem exclusão marcada) e com quem compartilhou ainda Analyst ou acima nela. O acesso só conta, e só vai para a Trilha de auditoria como `report.share_accessed`, depois de o arquivo ser entregue (ADR-0014). O histórico da Tela 19 traz os links ativos de cada relatório na própria listagem. Pedido, geração, compartilhamento e revogação também ficam na trilha (`report.requested`, `report.generated`, `report.shared`, `report.share_revoked`).

## Retenção

O Relatório segue o Incidente: quando a purga apaga o Incidente, a linha sai em cascata e o job diário remove o arquivo sem dono. Na exclusão total da Organização, o bucket entra com os outros, e o armazenamento conta na Cota `storage_bytes`.
