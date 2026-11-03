# Base de conhecimento

Exigem `Authorization: Bearer <JWT do Supabase Auth>` e Organização ativa. Todo Papel lê e busca; Analyst ou acima envia e remove (o banco confere o Papel na tabela).

| Rota | Efeito |
|---|---|
| `GET /api/v1/knowledge/documents` | Documentos da Organização, com status de indexação |
| `GET /api/v1/knowledge/global` | Documentos da Base global (só leitura) |
| `POST /api/v1/knowledge/documents` | `{ title, filename, content_type, size_bytes }` → `201` com `upload_url` (o navegador sobe o arquivo direto no bucket `doctor-knowledge`) |
| `POST /api/v1/knowledge/documents/{id}/finish` | Upload concluído → `202`; vai para a fila de indexação |
| `DELETE /api/v1/knowledge/documents/{id}` | Remove o documento, os Fragmentos e o arquivo → `204` |
| `POST /api/v1/knowledge/search` | `{ q, k }` → Fragmentos da Organização e da Base global, com a origem |

- **Formatos:** PDF, Markdown, TXT e DOCX, até 20 MB. PDF escaneado sem texto falha com mensagem clara.
- **Indexação** (worker de diagnóstico, `knowledge.index`): extrai o texto, **sanitiza antes do embedding** (segredo e dado pessoal nunca viram vetor), fragmenta por títulos e parágrafos (500 a 800 tokens, 80 de sobreposição) e gera o embedding com o provedor da Organização.
- **Busca** (`POST`, não `GET` como no ticket: a pergunta pode citar dado do cliente e não deve ir para a URL nem para os logs): RRF de quatro listas, vetor e texto (português) da Organização e da Base global. O vetor compara só Fragmentos do mesmo modelo de embedding. Com o provedor de IA fora, a busca segue só pelo texto (`mode: "text"`).
- **Isolamento:** o RAG nunca cruza Organizações: a consulta filtra a Organização explicitamente, além do RLS.
- **Troca de provedor:** o job `aid-knowledge-reindex` (Cloud Scheduler, de hora em hora) põe na fila os documentos cujo modelo de embedding não é o do provedor atual da Organização; até reindexar, eles só aparecem na busca por texto.
- **Base global:** textos originais da equipe em `packages/knowledge/src/aid_knowledge/global_base/`, gravados pelo job `python -m aid_knowledge.global_seed` no deploy (só refaz o que mudou).
