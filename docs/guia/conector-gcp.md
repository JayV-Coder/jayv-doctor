# Conector GCP (Cloud Logging)

O Conector lê os logs do projeto GCP onde a integração roda e os transforma em Eventos. Ele **só lê**: a Service Account precisa apenas de `roles/logging.viewer`.

1. No GCP do cliente, crie uma Service Account com `roles/logging.viewer` e gere a chave JSON.
2. No Doctor: **Conectores → Adicionar** (Owner ou Admin). O assistente tem quatro passos:
   - **Projeto:** o **ID do projeto** GCP e a **Integração vinculada**;
   - **Credencial:** cole a **Chave JSON da Service Account**; **Testar conexão** confere a chave e o acesso;
   - **Filtros de coleta:** o que ler, com um filtro avançado opcional (consulta do Logging), e o **Intervalo** da coleta. **Pré-visualizar** mostra uma amostra e uma estimativa do volume;
   - **Ativar:** **Ativar conector**.

A chave fica no cofre (Vault) e nunca volta para a tela. Cada coleta é uma **Sincronização**: a lista mostra quando rodou, quantos registros trouxe e o erro, se houver. **Sincronizar** roda uma coleta na hora.

- **Pausado por autenticação:** a chave foi revogada ou perdeu o papel. Gere outra e edite o Conector.
- **Em falha:** três falhas seguidas, com nova tentativa espaçada. O motivo aparece no Conector.
- **Cota de Eventos esgotada:** a coleta volta no mês seguinte ou com o aumento do plano (**Mais → Uso e cotas**).
