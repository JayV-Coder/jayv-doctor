# Link compartilhável do Relatório: token no fragmento e arquivo pelo proxy da API

O Relatório técnico (#32) tem um link opcional para quem não é da Organização: vale 7 dias, pode ser revogado e cada acesso fica na Trilha de auditoria. Uma URL assinada do Storage resolveria o download, mas não pode ser revogada antes de vencer e, por estar na própria URL, acaba em histórico, logs e cópias.

Por isso o link aponta para o app, `…/compartilhado#<token>`. O token fica no fragmento, que o navegador não envia ao servidor (como no aceite do convite). A página manda o token no corpo de um `POST /api/v1/shared-reports`, sem sessão, e a API:

1. calcula o sha256 do token e chama `doctor.open_report_share` como `anon` (a única porta anônima além da ingestão por token);
2. a função confere se o link está ativo, conta o acesso, grava `report.share_accessed` na trilha da Organização dona e devolve a URL assinada guardada;
3. a API busca o arquivo por essa URL e devolve os bytes. A URL nunca chega a quem tem o link.

A URL assinada é gerada na hora de compartilhar, com o JWT de quem compartilha (a política do bucket vale) e a mesma validade de 7 dias. A API não usa `service_role` (ADR-0004).

## Consequências

- Revogar ou vencer corta o acesso no mesmo instante, porque nada mais devolve a URL. Ela continuaria válida no Storage até vencer, mas só existe no banco: a coluna não é lida por `authenticated` e sai só pela função.
- O token não fica no banco (só o hash) nem nos logs de acesso do app ou da API, porque viaja no fragmento e no corpo.
- O download compartilhado passa pela API, o que custa banda da API. Os relatórios são pequenos (limite de 10 MB no bucket).
- O limite de requisições anônimas por IP é o do Cloud Armor, como na ingestão.
