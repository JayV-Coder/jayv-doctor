# Isolamento multi-tenant e checklist ASVS L2 (ticket #27)

Meta do piloto: **0 vazamento entre Organizações**. Este relatório junta o que o CI verifica a cada PR e o resultado do pentest interno guiado pelo OWASP ASVS 4.0.3, nível 2, seções V1 (arquitetura), V4 (controle de acesso) e V8 (proteção de dados). Data da revisão: 2026-11-03.

## O que o CI bloqueia

| Verificação | Onde | Asserções |
|---|---|---|
| Inventário das convenções: RLS em toda tabela do schema `doctor`, `tenant_id`, `unique (tenant_id, id)`, FK composta para tabela de tenant, política em toda tabela legível, partições inacessíveis direto, nada para `anon`, `security definer` com `search_path` fixo e sem `execute` para `public`, `anon` só nas 2 funções da ingestão; e uma tabela fora do padrão criada no próprio teste precisa ser detectada | `supabase/tests/database/30_conventions.test.sql` | 10 |
| Matriz de isolamento gerada por tabela: as 32 tabelas de tenant × `select`/`insert`/`update`/`delete`/mover linha de A para B × Owner, Admin, Analyst, Viewer de A contra dados de B (a fixture garante linha de B em todas) | `supabase/tests/database/31_isolation_matrix.test.sql` | 641 |
| Storage: ler, subir e apagar na pasta de B, nos buckets `doctor-raw-logs` e `doctor-knowledge`, por Owner, Analyst e Viewer de A | `supabase/tests/database/32_storage_isolation.test.sql` | 19 |
| API: as 31 operações com recurso no caminho, com o Owner (MFA) de A e o id de B → `404`, sem tocar no Storage nem no e-mail e sem mudar nada de B; rota nova com parâmetro fora da suíte quebra o teste | `apps/api/tests/test_api_isolation.py` | 33 |
| Isolamento por recurso já existente (RLS por tabela, RAG, Diagnóstico, worker) | testes pgTAP 02 a 22 (350 das 1.020 asserções do pgTAP), `packages/knowledge/tests/test_knowledge_db.py`, `workers/diagnosis/tests/test_diagnose.py` | 350+ |

Total de asserções de isolamento no banco: **≥ 670** só nos testes 30 a 32, todas passando.

O tenant nunca vem do payload: a API lê do JWT (`doctor.current_tenant_id()`), a ingestão do hash do token, e o worker de diagnóstico lê o contexto do Incidente com a claim do tenant (`aid_db.tenant_role`), com o RLS valendo como na API.

## Pendente fora do CI

- **Realtime:** o CI sobe o Supabase sem o serviço de Realtime. A garantia é a do próprio Supabase (`realtime.apply_rls` aplica as políticas com o JWT de quem assina), e a política de `doctor.diagnoses` e `doctor.incidents` é a mesma que a matriz testa no `select`. Verificar manualmente na janela de configuração: assinar `doctor.diagnoses` de B com o token de A não entrega eventos (em `docs/operations/pendencias.md`).
- **Advisors do Supabase** (security e performance): pedem o projeto real ou uma branch de preview, que o projeto compartilhado com o jayv-coder não usa (ADR-0009). Rodar na janela, antes do piloto.
- **Bucket `reports`:** chega com o relatório (#32); o teste 32 ganha o bucket junto.

## Checklist ASVS L2

Legenda: ✅ atende, com a evidência; ⚠️ atende em parte ou depende da configuração final; ➖ não se aplica nesta fase.

### V1 · Arquitetura

| Requisito | Status | Evidência |
|---|---|---|
| 1.1.2 Modelagem de ameaças por mudança | ⚠️ | Por ticket, nas ADRs e nas PRs; falta o documento de modelo de ameaças consolidado |
| 1.2.2 Comunicação entre componentes autenticada | ✅ | Pub/Sub push com OIDC, Cloud Run interno, Cloud Scheduler com OIDC (Terraform `stack/`) |
| 1.2.3 Um mecanismo de autenticação central | ✅ | Supabase Auth; a API valida JWT (JWKS) e o banco repete com `auth.jwt()` |
| 1.4.1 Controle de acesso aplicado num ponto confiável | ✅ | RLS no Postgres + `require_role` na API; funções `security definer` conferem o Papel na tabela |
| 1.4.4 Um único mecanismo de controle de acesso | ✅ | `doctor.has_member_role` / `require_manager` em todas as funções; matriz da API em `core/permissions.py` |
| 1.5.1 Entrada de dados não confiáveis tratada | ✅ | Pydantic com `extra=forbid` em todos os contratos; Sanitização antes de persistir e antes do LLM |
| 1.6.1 Política de chaves | ✅ | Segredos no Secret Manager e credenciais de Conector no Vault (ADR-0006); nenhum segredo no repositório (gitleaks no CI) |
| 1.8.1 Dados sensíveis identificados | ✅ | Referências de negócio como `hmac:` por tenant; PII sanitizada nos Eventos e na Base |
| 1.14.6 Sem tecnologias inseguras no cliente | ✅ | PWA sem armazenamento de token fora do cookie da sessão; termos de busca sensíveis por POST |

### V4 · Controle de acesso

| Requisito | Status | Evidência |
|---|---|---|
| 4.1.1 Controle de acesso no servidor | ✅ | Toda regra repetida no banco (RLS e funções); a UI só esconde botões |
| 4.1.2 Atributos de acesso não manipuláveis pelo cliente | ✅ | `tenant_id` só do JWT (Custom Access Token Hook) ou do token de ingestão; teste de transferência de linha na matriz |
| 4.1.3 Menor privilégio | ✅ | `authenticated` sem `insert`/`update`/`delete` direto na maioria das tabelas (escrita por funções); `service_role` só nos workers |
| 4.1.5 Falha segura | ✅ | Erro de banco sem mapeamento vira 500 genérico, sem detalhe; recurso de outra Organização é sempre 404 |
| 4.2.1 IDOR | ✅ | Suíte da API com os ids de B em todas as rotas; matriz do banco |
| 4.2.2 CSRF | ✅ | API por Bearer token (sem cookie); Server Actions do Next com verificação de origem |
| 4.3.1 Interfaces administrativas com MFA | ✅ | `require_manager` exige `aal2`, também no banco (`doctor.require_manager`) |
| 4.3.2 Sem listagem de diretórios / metadados | ✅ | Buckets privados, URLs assinadas de até 5 min, políticas por pasta do tenant |
| 4.3.3 Reautenticação para ações de alto valor | ⚠️ | MFA na sessão para ações administrativas; não há step-up por ação (avaliar no #38, SSO) |

### V8 · Proteção de dados

| Requisito | Status | Evidência |
|---|---|---|
| 8.1.1 Dados sensíveis fora de cache do servidor | ✅ | `cache: "no-store"` nas chamadas da web; cache do LLM escopado por Organização e sem conteúdo bruto |
| 8.1.2 Cópias temporárias protegidas | ✅ | Log bruto só no Storage privado, com retenção; texto bruto do documento promovido trocado pelo sanitizado e ilegível pelos membros |
| 8.2.1 Cabeçalhos anti-cache em respostas sensíveis | ⚠️ | Conferir os cabeçalhos do Cloud Run/Next na configuração final |
| 8.2.2 Nada sensível no armazenamento do navegador | ✅ | `localStorage` só para preferências (tema) |
| 8.3.1 Dados sensíveis no corpo, não na URL | ✅ | Buscas de Execuções, Incidentes e Base por POST |
| 8.3.2 Usuário pode exportar e apagar seus dados | ⚠️ | Exclusão e retenção chegam no #29 (LGPD) |
| 8.3.4 Dados sensíveis identificados e com política | ✅ | Tabela de retenção do PRD §8; Sanitização com relatório por Evento |
| 8.3.5 Acesso a dados sensíveis auditado | ✅ | Download do Log bruto, revisão do Diagnóstico, remoção e promoção na Base em `audit_logs` (append-only) |
| 8.3.7 Criptografia em repouso | ✅ | Supabase (Postgres e Storage) e Secret Manager com criptografia em repouso |

Nenhum vazamento entre Organizações encontrado. Achado corrigido nesta revisão: a troca para uma Organização sem Vínculo respondia `403`; agora responde `404`, como todo recurso de outra Organização (a resposta já era a mesma para Organização inexistente).
