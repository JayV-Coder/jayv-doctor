# Modelo local no cliente (ticket #46)

Decisão em [ADR-0019](../adr/0019-modelo-local-pelo-agente.md). Perfis de IA em [ia-perfis.md](ia-perfis.md).

## Requisitos no cliente

O servidor precisa ser compatível com a API da OpenAI (`POST /v1/chat/completions`) e aceitar `response_format` com `json_schema`: vLLM 0.6+ (saída guiada) ou TGI 2.x (gramática JSON).

| Modelo (open-weights) | GPU mínima | Memória da GPU | Observação |
|---|---|---|---|
| 8B (ex.: Llama 3.1 8B Instruct) | 1× L4 ou A10 | 24 GB | Só classificação e resumo; a avaliação do #47 decide se serve para o Diagnóstico |
| 70B quantizado em 4 bits (AWQ/GPTQ) | 2× L40S ou 1× H100 80 GB | 48–80 GB | Mínimo recomendado para o Diagnóstico |
| 70B em FP8 | 2× H100 80 GB | 160 GB | Melhor qualidade local |

CPU de 16 vCPUs, 64 GB de RAM e 200 GB de disco para os pesos. Os modelos recomendados e a diferença de qualidade contra os perfis em nuvem saem da avaliação do #47 (`aid_evaluation compare`).

## Ligar pelo agente

1. Suba o servidor na rede do cliente, alcançável pela máquina do agente (ex.: `http://vllm.interno:8000/v1`).
2. Na config do agente (Mais → Conectores → Agentes), acrescente o bloco `llm`:

   ```json
   { "collections": [...], "llm": { "base_url": "http://vllm.interno:8000/v1", "timeout_seconds": 120 } }
   ```

   HTTP vale, porque é a rede interna do cliente. A URL não aceita usuário e senha.
3. Com `service_role`: `select doctor.set_local_ai('<tenant>', 'agent', '<agent_id>', null, '<modelo servido>', 120);`
4. Peça um Diagnóstico híbrido de teste. No log do agente aparecem os pedidos atendidos; na plataforma, nenhum `ai.egress` dessa Organização.

## Ligar por endpoint privado

Com Private Service Connect até o servidor do cliente: `select doctor.set_local_ai('<tenant>', 'private_endpoint', null, 'https://<endereço privado>/v1', '<modelo>', 120);`. O worker só fala com esse host (`ai.egress` com `provider=local`).

## Degradação

Sem configuração, sem o agente ou sem resposta dentro do prazo, o Diagnóstico sai só com as Regras e avisa no card. Ele nunca vai a um provedor em nuvem. A Base de conhecimento desse perfil busca só pelo texto.

## Worker inteiro no cliente (alternativa)

Para quem não pode mandar nem o prompt sanitizado à plataforma: rode a imagem `aid-worker` com `WORKER_NAME=diagnosis` na rede do cliente, com acesso a uma réplica do banco da Organização e ao modelo local, e publique só o Diagnóstico na plataforma. É um projeto por cliente (rede, réplica, atualização da imagem), combinado com a operação, sem configuração pronta neste ticket.
