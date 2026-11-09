# Primeiros passos

## Entrar

Use o e-mail corporativo: **Enviar link de acesso** manda um link que entra sem senha, e **Entrar com senha** usa a senha da conta. Owner e Admin precisam de MFA: no primeiro acesso, o app pede para cadastrar um aplicativo autenticador (**Gerar QR code**). Guarde o fator reserva que aparece no cadastro.

## Organização

Cada empresa é uma **Organização**, e os dados de uma nunca aparecem para outra. Quem cria a Organização vira **Owner**. Se você participa de mais de uma, troque pelo seletor no topo da tela.

| Papel | Pode |
|---|---|
| Owner | tudo, inclusive excluir a Organização |
| Admin | membros, Integrações, Conectores, retenção e auditoria (com MFA) |
| Analyst | importar logs, pedir e revisar Diagnósticos, gerar Relatórios |
| Viewer | ler Incidentes, Diagnósticos e Relatórios |

Para chamar a equipe: **Mais → Membros e convites → Enviar convite**. O convite vale 7 dias.

## A primeira Integração

Uma **Integração** é um fluxo entre dois sistemas, como "Pedidos Salesforce → SAP" em produção. Em **Mais → Integrações → Nova integração**, informe nome, origem, destino e ambiente. As Execuções e os Incidentes são sempre de uma Integração.

Depois, escolha como os Eventos chegam:

- [Conector GCP](conector-gcp.md): o Doctor lê o Cloud Logging de tempos em tempos;
- [Importação](importacao.md): você envia um arquivo de logs;
- API de ingestão: o seu sistema envia os Eventos ([guia técnico](../api/ingestion.md)).
