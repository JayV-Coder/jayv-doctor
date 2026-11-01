# Doctor no schema `doctor` do projeto Supabase do jayv-coder

O Doctor usa o projeto Supabase `exvsozyemolrjbjetqww`, o mesmo do jayv-coder em produção, em `sa-east-1`. Tudo o que é dele fica no schema `doctor`, que substitui o schema `app` previsto no PRD e nos tickets. O Doctor compartilha três tabelas de `public` e não altera nenhuma delas:

- `public.profiles`: perfil do Usuário, criado pelo trigger do jayv-coder.
- `public.organizations`: nome e slug. `doctor.tenants` estende cada linha com o que é do Doctor, e só Organizações com linha ali usam o produto.
- `public.organization_members`: o Vínculo. Os Papéis de lá são `owner`, `maintainer` e `member`, então o Papel do Doctor fica em `doctor.memberships`, com FK composta para o Vínculo. Remover alguém no jayv-coder remove o acesso ao Doctor, e estar em `public` não dá acesso ao Doctor.

Criar uma Organização passa por `public.create_organization`, para manter as regras do jayv-coder. Por isso nome e slug seguem os limites de lá: 80 e 40 caracteres.

## Consequências

- **Migrações:** ficam fora de `supabase_migrations.schema_migrations`, que é do jayv-coder. Quem aplica é `scripts/apply-doctor-migrations.py`, nunca `supabase db push`. Para chegar a este desenho, editamos migrações já aplicadas no antigo projeto dev, que foi abandonado: é a única exceção à regra de não editá-las.
- **Extensões:** instalar uma exige aprovação, porque afeta o banco do jayv-coder. `vector` e `pg_partman` entram nos tickets que as usarem.
- **Apagar uma Organização habilitada no Doctor é recusado** no jayv-coder (`on delete restrict`), com erro de FK, até haver desprovisionamento. Diagnósticos são imutáveis e o aceite do DPA é evidência.
- **Stack local:** `00000000000000_shared_public_stub.sql` copia o mínimo de `public` e nunca vai para o projeto hospedado. Mudanças do jayv-coder nessas tabelas precisam ser refletidas nele à mão.
- **Auth é um só:** hook de JWT, templates de e-mail, URLs de redirecionamento e política de senha valem para os dois produtos. O hook não pode derrubar o login: em erro de banco, devolve o token sem claims de tenant, e o RLS do Doctor nega tudo. O Supabase aceita um hook por projeto: se o jayv-coder passar a precisar de outro, os dois terão de virar um.
- **Ambientes:** dev, staging e prod do GCP apontam para o mesmo banco enquanto não houver outro projeto Supabase.

## Considered Options

- **Alterar o check de Papel em `public.organization_members`:** obrigaria mudar todo código do jayv-coder que lê o campo.
- **Organizações próprias no Doctor:** isolamento maior, mas sem conta de organização comum entre os produtos.
