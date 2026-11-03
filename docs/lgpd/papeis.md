# Controlador e operador

- **Controlador:** a empresa cliente (a Organização). Ela decide quais integrações monitorar, quais logs enviar, por quanto tempo guardar (dentro dos limites do produto) e se as evidências podem ir a um provedor de IA.
- **Operador:** o Integration AI Doctor. Trata os dados só para diagnosticar falhas das integrações do cliente, conforme as instruções do controlador registradas no produto (retenção, envio ao LLM, exclusão).
- **Suboperadores (subprocessadores):** Supabase, Google Cloud e o provedor de IA da Organização (Anthropic e Voyage AI, ou Google Vertex AI em São Paulo). Lista em Mais › Subprocessadores.

## Que dado pessoal passa pelo Doctor

Os logs de integração podem conter dado pessoal de terceiros (clientes do cliente): nome, e-mail, telefone, CPF/CNPJ, endereço, número de pedido. O Doctor:

- sanitiza antes de gravar o Evento e antes de qualquer envio a IA (tokens, senhas, CPF/CNPJ, e-mails, telefones e cartões saem; o relatório da Sanitização fica no Evento);
- guarda a Referência de negócio (ex.: nº do pedido) só como HMAC com a chave da Organização;
- mantém o Log bruto (o arquivo original) no Storage privado, pelo prazo da retenção (padrão 30 dias), e só Analyst ou acima o baixa, com auditoria.

Dos Usuários do Doctor, guarda e-mail, nome de exibição, Papel e os registros da Trilha de auditoria (365 dias).

## Instruções do controlador no produto

| Instrução | Onde | Quem |
|---|---|---|
| Retenção por classe de dado | Mais › Retenção | Owner ou Admin com MFA |
| Enviar evidências ao LLM (liga/desliga) | Mais › LGPD e IA | Owner ou Admin com MFA |
| Localizar e apagar os Eventos de um titular | Mais › Direitos do titular | Owner ou Admin com MFA |
| Exclusão total da Organização (7 dias de carência) | Mais › Solicitar exclusão total | Owner com MFA |

Todas ficam na Trilha de auditoria.
