# O app do Doctor no site da JayV

As telas do Doctor saem de `apps/web` e passam a morar no `site` (JayV-Coder/site), em `/[locale]/doctor`. O site já tem a conta, o login com MFA, a troca de Organização, o i18n em dez idiomas e o design system. O Doctor era a única parte com um segundo app Next.js, com login próprio sobre o mesmo Supabase Auth.

O site fala com esta API pelo servidor (`DOCTOR_API_URL`), com o JWT da sessão, como o `apps/web` fazia. A API, os workers e o banco não mudam.

## Consequências

- **`APP_URL` é a origem do site.** Os endereços que a plataforma manda para fora ficam em `aid_alerts.links` (`app_link`), com o prefixo `/doctor`:
  - alertas;
  - webhooks;
  - chamados no Jira e no ServiceNow;
  - convite (`/doctor/invitations/accept#…`);
  - link do relatório (`/doctor/shared#…`).

  Sem o idioma no caminho, o site manda para o da pessoa e mantém a query. O fragmento fica com o navegador, então o token do convite e o do relatório continuam fora dos logs (ADR-0014).
- **A volta do consentimento do Jira** passa a ser `APP_URL/doctor/tickets/jira`, o que muda o app OAuth no Atlassian e `AID_ATLASSIAN_REDIRECT_URI`.
- **Textos** ficam na tabela de traduções do site (`public.translations`, chaves `site.doctor.*`), em migrações `<versão>_site_doctor_<nome>.sql` no JayV-Coder/supabase, aplicadas no merge.
- **`apps/web` sai** quando a última tela chegar ao site, junto com:
  - o job de E2E;
  - o serviço `web` do Dokploy;
  - o serviço `web` no Cloud Run.

## Considered Options

- **Manter `apps/web` com o visual do site:** dois apps Next.js, dois logins e duas cópias de i18n e design system para o mesmo usuário.
- **Subdomínio próprio servido pelo site:** o mesmo código, com um domínio a mais para manter, cookies separados e nada a ganhar.
