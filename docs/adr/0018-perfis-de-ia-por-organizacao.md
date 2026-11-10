# Perfis de IA por Organização: padrão, Brasil e dedicado

A Organização escolhe um **perfil de IA**, que diz onde as Evidências sanitizadas são processadas. O perfil substitui a escolha direta do provedor (ADR-0007), que passa a ser derivada dele:

| Perfil | Geração | Embeddings | Onde |
|---|---|---|---|
| `standard` | Claude (API da Anthropic) | Voyage | EUA |
| `br_region` | Gemini no Vertex AI | `text-embedding-005` no Vertex AI | `southamerica-east1` |
| `dedicated` | Gemini no Vertex AI com **Provisioned Throughput** (`X-Vertex-AI-LLM-Request-Type: dedicated`, sem transbordo para a capacidade compartilhada) | `text-embedding-005` no Vertex AI | `southamerica-east1`, no projeto da plataforma ou do cliente (`ai_project`) |

O Owner com MFA troca entre `standard` e `br_region`. O `dedicated` depende de capacidade contratada e é ligado pela operação da plataforma (`doctor.set_dedicated_ai`, só `service_role`); o Owner pode sair dele.

O que garante e comprova que um perfil no Brasil não sai do Brasil:

- O provedor do Vertex só aceita a região `southamerica-east1` e só fala com o endpoint regional (`southamerica-east1-aiplatform.googleapis.com`) e com o servidor de metadados. Pedido para qualquer outro host é recusado antes de sair.
- Toda chamada de IA registra um log estruturado `ai.egress` com o provedor, o host e a região, sem conteúdo. Uma métrica de log alerta se um provedor do Brasil registrar host fora dele.
- Um job diário (`POST /ai/verify` no worker `diagnosis`) chama cada perfil em uso com uma pergunta fixa, confere os hosts e a região efetivos e grava o resultado em `doctor.ai_profile_checks`. Divergência gera o log `ai.profile_divergence`, que dispara alerta.

Trocar de perfil pode trocar o modelo de embedding. Os documentos são reindexados em segundo plano (`reindex_stale`), e a tela mostra o progresso. Até terminar, a busca também consulta o índice antigo, **desde que o provedor dele seja permitido pelo perfil novo**. Quem passa para `br_region` não consulta mais o Voyage: os Fragmentos antigos seguem achados pelo texto até o reindex terminar.

## Consequências

- Os subprocessadores e o DPA exibidos seguem o perfil.
- A avaliação (#30) roda por perfil (`--profile`), e `aid_evaluation compare` publica a diferença de qualidade e de custo entre os relatórios.
- Provisioned Throughput sem capacidade disponível responde 429. O Diagnóstico entra no modo degradado (`rules_only`) em vez de usar a capacidade compartilhada.
