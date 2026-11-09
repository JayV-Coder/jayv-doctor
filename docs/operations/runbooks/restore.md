# Recuperação: banco (PITR) e arquivos do Storage

Runbook do ticket #33. Vale para o Doctor no projeto Supabase compartilhado com o jayv-coder (ADR-0009): **restaurar o projeto inteiro também volta os dados do jayv-coder**. Por isso, a recuperação do Doctor é sempre para um **projeto novo**, de onde se copia o schema `doctor`.

## Objetivos

| | Meta | Como |
|---|---|---|
| **RPO do banco** | ≤ 2 min | PITR do Supabase (WAL contínuo) |
| **RTO do banco** | ≤ 4 h | restaurar em projeto novo + copiar o schema `doctor` |
| **RPO dos arquivos** | ≤ 24 h | espelho diário no GCS (`<projeto>-storage-backup`, 04:00 BRT) |
| **RTO dos arquivos** | ≤ 2 h | cópia de volta do GCS para os buckets `doctor-*` |

Os valores medidos no drill ficam no [registro](#registro-dos-drills).

## Pré-requisitos

- PITR habilitado no projeto de produção (add-on pago; decisão conjunta com o jayv-coder).
- Acesso de Owner ao projeto Supabase e `roles/storage.objectViewer` no bucket de backup.
- `SUPABASE_DB_URL` de origem e de destino como variáveis de ambiente, nunca coladas em chat ou ticket.

## Drill de restauração (trimestral, e antes da liberação do MVP)

1. **Escolha o ponto no tempo** `T` (ex.: 30 min atrás) e anote-o em UTC.
2. **Impressão digital da origem até `T`:**
   ```bash
   SUPABASE_DB_URL=$ORIGEM uv run python scripts/db_fingerprint.py take --until "$T" > origem.json
   ```
3. **Restaure para um projeto novo** no painel do Supabase (Database → Backups → Point in time → *Restore to a new project*), no ponto `T`, na mesma região (`sa-east-1`). Marque o horário de início.
4. **Impressão digital do restaurado e comparação:**
   ```bash
   SUPABASE_DB_URL=$RESTAURADO uv run python scripts/db_fingerprint.py take --until "$T" > restaurado.json
   uv run python scripts/db_fingerprint.py compare origem.json restaurado.json   # "íntegro" ou as diferenças
   ```
   A comparação usa a contagem de cada tabela do schema `doctor` (até `T`, pelas que têm `created_at`) e o md5 de uma amostra de 1.000 linhas. Filas e agregados que mudam sozinhos (outbox, idempotência, deltas de uso) entram só pela contagem. Uma linha alterada depois de `T` aparece como "amostra diferente": confira se a alteração é posterior ao ponto antes de tratar como falha.
5. **Arquivos:** copie uma pasta de Organização do bucket de backup para um bucket temporário e confira o sha256 de uma amostra contra o original (`gcloud storage hash`).
6. **Meça e registre** RTO (do passo 3 até o passo 4 íntegro) e RPO (`T` menos o último dado presente no restaurado) no registro abaixo.
7. **Apague o projeto restaurado** e o bucket temporário: eles têm dados de clientes.

## Recuperação de verdade

1. **Declare o incidente** e congele as escritas do Doctor: Cloud Scheduler pausado (relay, Conectores, retenção, backup) e a API com `min/max instances = 0`. O jayv-coder continua no ar.
2. Siga os passos 1 a 4 do drill, com `T` logo antes do problema.
3. **Copie o schema `doctor`** do projeto restaurado para o de produção:
   ```bash
   pg_dump "$RESTAURADO" --schema=doctor --data-only --disable-triggers -Fc -f doctor.dump
   # no projeto de produção, numa janela combinada: esvazie as tabelas do doctor e restaure
   pg_restore -d "$PRODUCAO" --data-only --disable-triggers doctor.dump
   ```
   Nunca `supabase db push` nem `drop schema public`: o `public` é do jayv-coder.
4. **Arquivos:** copie do espelho para os buckets `doctor-*` só o que falta. Versões antigas ficam 7 dias, e o que a LGPD mandou apagar depois de `T` **não volta**: refaça as exclusões do período pela Trilha de auditoria (`subject.erased`, `tenant.deleted`).
5. Rode `scripts/db_fingerprint.py compare` entre o restaurado e a produção, retome os jobs e a API, e acompanhe a outbox até ela esvaziar.

## Registro dos drills

| Data | Ponto `T` | RTO medido | RPO medido | Resultado | Responsável |
|---|---|---|---|---|---|
| — | — | a medir | a medir | pendente | — |
