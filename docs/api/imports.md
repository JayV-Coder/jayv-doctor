# Importação manual

Exigem `Authorization: Bearer <JWT do Supabase Auth>` e Organização ativa. Todo Papel lista. Importar é de Owner, Admin e Analyst, sem exigir MFA, conforme a linha "Importar logs" da matriz do ticket #6. O banco confere de novo o Papel, lido da tabela.

| Rota | Efeito |
|---|---|
| `GET /api/v1/imports` | As 50 Importações mais recentes da Organização ativa |
| `POST /api/v1/imports` | Cria a Importação → `201 { id, status, error, duplicate_of }` |
| `POST /api/v1/imports/{id}/upload-url` | URL assinada para subir o arquivo de uma Importação `pending` → `200 { upload_url }`; pode ser repetida para reenviar |
| `POST /api/v1/imports/{id}/complete` | Confere o arquivo no Storage e enfileira o processamento → `200` com a Importação |

Fluxo:

1. O navegador calcula o sha256 do arquivo e chama `POST /imports` com `{ integration_id, filename, size_bytes, sha256 }`.
2. A Importação pode nascer `rejected` por quatro motivos:
   - extensão fora de `.json`, `.ndjson` e `.csv`: "Formato não permitido";
   - arquivo vazio;
   - arquivo acima de 50 MB;
   - mesmo sha256 já importado na mesma Integração: "Arquivo já importado nesta Integração", com `duplicate_of`.
3. Se não for recusada, nasce `pending`, já com um Log bruto que vence em 1 dia. O navegador pede a URL assinada (`upload-url`) e sobe o arquivo direto no Storage, com `PUT`, sem passar pela API, para `doctor-raw-logs/{tenant_id}/imports/{import_id}/upload.{formato}`. O nome original fica só no banco, então acento e espaço não chegam à chave do Storage. Se o upload nunca terminar, a retenção (ticket #29) apaga o que tiver chegado.

   A URL tem rota própria porque o Storage confere a política de upload na conexão dele. Ele só enxerga a Importação depois do commit, e com `Idempotency-Key` a criação fica numa transação ainda aberta.
4. `POST /imports/{id}/complete`: a API lê os primeiros 64 KB do objeto com o JWT do Usuário, então as políticas do bucket valem. Ela confere:
   - os magic bytes: um binário renomeado é recusado;
   - o parse do começo: JSON começando por `[` ou `{`, a primeira linha do NDJSON como objeto, e o cabeçalho do CSV com `,`, `;` ou tab;
   - UTF-8 com ou sem BOM, ou Latin-1.

   Se o conteúdo não bater com a extensão, a Importação vira `rejected` com "Conteúdo não corresponde ao formato", e o objeto é registrado como Log bruto já vencido, para a retenção apagá-lo. Se bater, ainda confere a duplicidade de novo: duas abas podem subir o mesmo arquivo ao mesmo tempo, e a segunda a concluir vira duplicada. Não sendo duplicada, vira `uploaded`, o Log bruto passa a valer 30 dias e uma mensagem `ingestion.raw` vai para a outbox, tudo na mesma transação.
5. O worker de ingestão (ticket #12) faz o parse completo em streaming, a Sanitização e a deduplicação. Ele também preenche `total_lines`, `accepted`, `rejected`, `duplicates` e `secrets_removed`, e leva o status a `processing`, `done` ou `failed`.

O tenant e o caminho no Storage nunca vêm do payload: campos extras viram `422`. No Storage, só quem importa lê o Log bruto, e só na pasta da Organização ativa. O objeto só entra no caminho de uma Importação `pending` da própria Organização.

## Erros (`application/problem+json`)

| Status | `code` | Quando |
|---|---|---|
| 401 | `unauthorized` | Token ausente, inválido ou expirado |
| 403 | `no_active_tenant` | Sem Organização ativa |
| 403 | `forbidden` | Papel não importa logs |
| 404 | `not_found` | Integração ou Importação inexistente (ou arquivada) nesta Organização |
| 409 | `import_not_pending` | `upload-url` ou `complete` numa Importação já concluída ou recusada |
| 409 | `upload_missing` | `complete` antes de o arquivo chegar ao Storage |
| 422 | `validation_error` | Corpo inválido |
| 422 | `invalid_filename` | Nome de arquivo com caminho ou caractere de controle |
| 503 | `storage_unavailable` | Storage fora do ar; tente de novo |
