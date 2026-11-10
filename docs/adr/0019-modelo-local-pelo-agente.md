# Modelo local no cliente: pelo agente, sem cair na nuvem

Clientes em rede isolada pedem que nenhuma Evidência saia da rede deles nem para o provedor de IA. O perfil `local` (ADR-0018) atende isso com um servidor compatível com a API da OpenAI (vLLM ou TGI) **dentro da rede do cliente**. A orquestração continua na plataforma: Regras, correlação, verificação das Evidências e publicação. Só o prompt (Evidências já sanitizadas e delimitadas) vai ao modelo, e só a resposta estruturada volta.

**Caminho.** O agente local (#39, ADR-0015) não abre porta de entrada, e a plataforma não alcança a rede do cliente. Então o pedido faz o caminho contrário:

1. O worker `diagnosis` põe o pedido em `doctor.local_llm_requests` (o corpo de um chat completion).
2. O agente da Organização busca o próximo pedido por long-poll (`GET /api/v1/agent/llm`, assinado como as outras rotas do agente) e chama o servidor da rede do cliente (`llm.base_url` na config do agente, validada pela allowlist). Só os campos de chat seguem (`model`, `messages`, `response_format`, `max_tokens`, `temperature`).
3. O agente devolve a resposta (`POST /api/v1/agent/llm/{id}`), e o worker a lê e apaga a linha. Prompt e resposta não ficam no banco.

A alternativa é um endpoint privado (Private Service Connect): o worker chama direto, e o cliente HTTP só aceita aquele host. A operação da plataforma liga o modo local com `doctor.set_local_ai` (só `service_role`), porque ele depende do servidor e do agente no cliente.

**Sem queda para a nuvem.** O registro dos provedores em nuvem recusa montar o perfil `local` (falha fechada). Sem configuração, sem agente ou sem resposta no prazo (`timeout_seconds`, padrão 120 s), o Diagnóstico sai só com as Regras (`failed_llm` ou `rules_only`, com o aviso), e nunca passa a outro provedor. O teste de contrato roda o Diagnóstico com um registro que falha se for chamado e confere que nenhum egress de IA saiu da plataforma.

**Sem embeddings.** O perfil local não gera embeddings: a Base de conhecimento dele busca só pelo texto, e a pergunta não sai da plataforma.

## Consequências

- A latência inclui o long-poll do agente (até 1 s para pegar o pedido) e a inferência local. O prazo é por Organização.
- `anon` ganha `claim_local_llm` e `finish_local_llm`, ambas exigindo o hash do segredo do agente e servindo só pedidos da Organização dele.
- Quem não pode nem mandar o prompt sanitizado à plataforma roda o worker `diagnosis` inteiro na própria rede (a mesma imagem `aid-worker`), e a plataforma só recebe o Diagnóstico publicado. Esse modo é documentado em `docs/operations/ia-local.md` e configurado caso a caso.
