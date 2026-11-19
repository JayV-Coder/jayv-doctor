# Leituras do site direto no Supabase, escritas pela API

A API do Doctor roda no Railway, nos EUA, e o banco fica em São Paulo. Cada comando custa duas idas e voltas de ~165 ms, e as páginas do Doctor levavam de 2 a 5 s. A partir daqui:

- **O site lê direto no Supabase**, pelo PostgREST, com o token de quem entrou. As leituras ficam no schema `doctor_read`, que é o único exposto na API de dados, com uma função por tela que devolve tudo de uma vez: `me`, `dashboard` e `incidents` neste primeiro bloco. As funções rodam com o RLS de quem chama. Se a leitura direta falhar, por exemplo com o schema ainda não exposto, o site volta para a API.
- **As escritas continuam pela API**: idempotência, auditoria com IP, Vault, links assinados do Storage, OAuth do Jira, cotas e Diagnóstico.
- **O processamento continua nos workers** (outbox, RabbitMQ). O site fica sabendo das mudanças pelo **Realtime** do Supabase (`postgres_changes` nas tabelas da Organização ativa), em vez de reler a página de tempos em tempos.

## Consequências

- **A Organização do JWT só vale com Vínculo vivo.** O token dura até 1 h. A API já conferia o Vínculo a cada pedido; agora `doctor.current_tenant_id()` confere no banco, e todas as políticas de RLS e o Realtime barram quem foi removido sem esperar o token vencer. Quem age sem Usuário (os workers, com a claim do tenant) segue como antes.
- **O schema `doctor` continua fora da API de dados.** O `anon` executa nele as funções por token (ingestão, SCIM, agente, webhooks de ITSM), que só a API deve chamar. O `doctor_read` não dá nada ao `anon`.
- **A busca de Incidentes por texto continua pela API.** Ela precisa do HMAC da Referência de negócio, e a chave fica só na API. Leituras auditadas, como o download do log bruto, também.
- **O token vai ao navegador para o Realtime.** Ele já estava acessível pela sessão do NextAuth (`/api/auth/session`); o socket o usa e o renova a cada 30 min.
- **Duas implementações da mesma leitura** (API e `doctor_read`) até a API passar a chamar as mesmas funções.
- **Em produção**, `doctor_read` precisa estar em "Exposed schemas" (Settings → Data API).

## Considered Options

- **Só otimizar a API no Railway** (pool, menos comandos): reduz, mas cada página continua com várias idas e voltas entre os EUA e São Paulo.
- **Levar a API para São Paulo** (GCP, Fly.io): resolve a distância sem mudar a arquitetura. Pode vir depois; as leituras diretas continuam valendo.
- **Expor o schema `doctor`:** abriria as funções de `anon` e todas as tabelas pela API de dados.
