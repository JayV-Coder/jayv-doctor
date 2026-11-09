# Importação de logs

Para trazer o histórico (por exemplo, os incidentes das últimas semanas no piloto) ou integrar um ambiente sem Conector.

1. **Conectores → Importar logs** (Analyst ou acima).
2. Escolha a **Integração** e o arquivo: JSON, NDJSON (um Evento por linha, no [Contrato de evento](../api/ingestion.md)) ou CSV com as mesmas colunas. O limite é de 50 MB por arquivo.
3. **Escolher arquivo** e enviar. O arquivo vai direto para o armazenamento da sua Organização, e o progresso aparece na tela.

Cada linha é validada e sanitizada: segredos e dados pessoais saem antes de gravar, e a Referência de negócio (nº do pedido, por exemplo) vira um código (HMAC) que só a sua Organização consegue procurar. As linhas recusadas aparecem com o número e o motivo, sem o conteúdo.

O arquivo original fica guardado pela retenção da Organização (30 dias por padrão) e pode ser baixado pelo Explorador de Execuções, com registro na Trilha de auditoria.
