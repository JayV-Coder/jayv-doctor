# Alertas num worker próprio, alimentado por trigger na outbox

O #41 entrega notificações por push no PWA, e-mail, Slack e Microsoft Teams. Os webhooks do Slack e do Teams são segredos: quem tem o endereço posta no canal do cliente. A chave privada VAPID assina todos os pushes da plataforma. Pôr esses segredos num worker que já existe aumentaria o alcance de um vazamento. O worker de diagnóstico fala com o LLM, e o de Conectores tem as credenciais dos sistemas dos clientes.

Então os alertas ficam num worker próprio, `notifier`, com conta de serviço própria e só os segredos dele (`smtp-url`, `vapid-private-key` e a leitura dos webhooks no Vault por `doctor.get_channel_secret`).

**Entrada.** Um tópico só, `alert.evaluate`, criado na mesma transação do fato que pode notificar:

- trigger na outbox: `incident.opened` e `incident.updated` geram também `alert.evaluate`, com o tópico de origem no `source`;
- trigger em `connectors`: a mudança para `failing` gera `alert.evaluate` com `connector.failing`;
- os dois triggers só gravam quando a Organização tem Regra ligada do tipo: sem Regra, nenhuma mensagem a mais;
- varredura agendada (`POST /alerts/scan`, a cada minuto): taxa de erro por Integração e Diagnóstico aguardando revisão, que dependem do tempo, não de um evento.

O trigger evita espalhar o envio por todos os lugares que já gravam essas mensagens e não deixa um caminho novo esquecer o alerta.

**Deduplicação.** Cada notificação tem um assunto (`incident:<id>:<severidade>`, `connector:<id>`, `error_rate:<integração>`, `diagnosis:<id>`). Sob um lock por assunto na Organização, cada canal recebe o assunto no máximo uma vez a cada 15 min, mesmo com duas Regras sobrepostas no mesmo canal; o resto vira `suppressed` no histórico. O Diagnóstico aguardando revisão notifica uma vez só. 37 Execuções no mesmo Incidente geram uma notificação. A severidade entra no assunto: o Incidente que escala para crítico notifica de novo.

A reserva (`pending`) sai antes do envio e vence em 2 min, para uma queda do worker no meio não esconder a notificação. Canal que falhou espera 5 min antes de nova tentativa. Qualquer falha de um canal vira `failed` dele, e os outros seguem. O histórico guarda 30 dias.

**Latência.** O relay drena a outbox numa rodada de 40 s por minuto e, com `follow`, continua olhando a cada 2 s até o fim da rodada. Um Incidente crítico sai em segundos, ou nos 20 s entre rodadas, e não espera o minuto seguinte.

**Conteúdo.** Só título, severidade, Integração, Ambiente e o link para o Incidente. Nada de log, Evidência ou dado de negócio, porque a mensagem aparece em Slack, Teams, e-mail e na tela de bloqueio do celular.

## Consequências

- Um sexto worker no Cloud Run, com `max_instances = 1`: o volume é baixo e o lock serializa por assunto. A soma de conexões continua na fatia do Supavisor (`docs/operations/capacity.md`).
- O relay faz até 20 consultas extras por minuto à outbox vazia: uma consulta indexada a cada 2 s.
- Slack entra por Incoming Webhook (o app do Slack gera o endereço na instalação); o fluxo OAuth de instalação do app fica para quando houver o app publicado. Teams, por Incoming Webhook ou Workflows. Os hosts aceitos são fixos (`hooks.slack.com`, `*.webhook.office.com`, `*.logic.azure.com`, `*.powerplatform.com`).
- Um aparelho é de quem o assinou por último: a assinatura do mesmo endpoint de outro Usuário sai (`doctor.claim_push_endpoint`), e sair da conta cancela o push do navegador.
- E-mail sai um por destinatário: ninguém vê o endereço dos colegas. Os envios ficam fora da transação do banco.
- O texto que vai ao Slack escapa `&`, `<` e `>`: o nome da Integração vem do cliente e não vira menção nem link disfarçado.
- O `endpoint` do push vem do navegador, e o `notifier` faz POST nele. Só os serviços de push dos navegadores são aceitos (Google, Mozilla, Apple, Microsoft), na API e de novo no envio; um endpoint qualquer seria SSRF a partir da plataforma.
