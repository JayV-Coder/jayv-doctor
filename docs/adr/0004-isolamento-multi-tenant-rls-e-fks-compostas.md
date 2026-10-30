# Isolamento por RLS, FKs compostas com tenant_id e tenant vindo só do JWT

Toda tabela operacional tem `tenant_id`, `UNIQUE (tenant_id, id)` e chaves estrangeiras compostas `(tenant_id, x_id)`. Assim o banco recusa relacionamentos entre Organizações mesmo com um bug na aplicação. O RLS filtra por `app.current_tenant_id()`, que lê a claim `tenant_id` do JWT, injetada pelo *Custom Access Token Hook* do Supabase a partir da Organização ativa. A API FastAPI **não** usa `service_role` para requisições de usuário: abre cada transação com `SET LOCAL role authenticated` e `set_config('request.jwt.claims', …)`, então o RLS também vale na API. Workers usam claims de serviço com escopo de um tenant. O `tenant_id` de payloads externos nunca é aceito. Testes de isolamento rodam obrigatoriamente no CI.

## Considered Options
- **Schema por tenant**: as migrações custam N vezes mais e não combinam com PostgREST e Realtime.
- **Filtro só na aplicação**: um único `WHERE` esquecido vaza dados. A meta do PRD é zero vazamento.
