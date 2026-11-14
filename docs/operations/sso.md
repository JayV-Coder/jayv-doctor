# SSO: ligar no projeto Supabase

O SSO de uma Organização só fica ativo depois que a plataforma registra o provedor SAML no Supabase Auth do projeto ([ADR-0021](../adr/0021-sso-saml-pelo-supabase-auth.md)). O projeto é compartilhado com o jayv-coder: tudo aqui exige janela combinada.

1. Confirmar que o projeto está no plano Pro (o SAML do Supabase Auth exige) e ligar o SAML em Authentication → Providers → SAML 2.0.
2. Gerar um token pessoal da Management API (Account → Access Tokens) com acesso só a esse projeto e gravá-lo no segredo `supabase-access-token` (GCP) ou em `SUPABASE_ACCESS_TOKEN` (Dokploy). `SUPABASE_PROJECT_REF` é o ref do projeto.
3. Com o token, cada `PUT /api/v1/sso` ou domínio verificado gera um `sso.sync`, e o `notifier` cria ou atualiza o provedor. A conexão passa a `active`, ou a `error` com o motivo em `last_error`.
4. Conexões que ficaram `pending_platform` antes do token: reenvie com `insert into doctor.outbox_messages (tenant_id, topic, payload) select tenant_id, 'sso.sync', jsonb_build_object('connection_id', id) from doctor.sso_connections where status = 'pending_platform';`.

## No IdP da Organização

- **Entity ID e ACS:** os do Supabase Auth do projeto (`https://<ref>.supabase.co/auth/v1/sso/saml/metadata` e `…/acs`).
- **Atributos:** e-mail e `groups` (multivalorado). O mapeamento grupo → Papel é feito na tela de SSO.
- **SCIM:** base `https://<API>/scim/v2` e o token gerado na tela; atributos `userName` (e-mail) e `active`.

## Acompanhar

- "Exigir SSO" só passa a valer com a conexão `active`; enquanto ela está `pending_platform` ou `error`, a senha continua abrindo o Doctor.
- Domínio que não verifica: o TXT `_aid-sso.<domínio>` precisa ter exatamente `aid-sso=<token>`; a consulta é feita pelo DNS público do Google. Se ele não responder, a mensagem volta para a fila e tenta de novo. Um domínio verificado não perde a verificação sozinho.
- Provedor no Supabase: a remoção só conta quando a Management API confirma; se a Organização desligar o SSO no meio do registro, o worker apaga o provedor recém-criado. Numa reentrega, ele atualiza o provedor que já tem o domínio, em vez de criar outro.
- Remoção pelo SCIM: o Vínculo some na hora, e o JWT já emitido é recusado pela API (`membership_revoked`) no pedido seguinte. As sessões no Auth são apagadas só para e-mails de domínio verificado da Organização.
- IdP fora do ar com "Exigir SSO" ligado: o Owner entra por senha (com MFA) e desliga a regra na tela de SSO.
