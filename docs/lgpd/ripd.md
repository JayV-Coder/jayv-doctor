# Relatório de impacto à proteção de dados (RIPD)

**Tratamento:** diagnóstico de falhas de integrações a partir de logs técnicos. **Versão:** 1.0 (piloto). **Revisão:** a cada mudança de subprocessador, de finalidade ou de categoria de dado.

## Descrição

| Item | Conteúdo |
|---|---|
| Finalidade | Encontrar a causa provável de falhas de integração e recomendar ações humanas |
| Base legal (controlador) | Legítimo interesse ou execução de contrato com o titular, conforme a operação do cliente; o operador segue as instruções |
| Titulares | Clientes, fornecedores e colaboradores do controlador cujos dados aparecem nos logs; Usuários do Doctor |
| Categorias | Identificadores e contato que aparecem em logs (nome, e-mail, telefone, CPF/CNPJ, nº de pedido); não se espera dado sensível do art. 5º, II |
| Volume | Proporcional ao volume de integrações do controlador |
| Retenção | Configurável por classe, com os padrões do PRD §8 |

## Riscos e medidas

| Risco | Medida | Risco residual |
|---|---|---|
| Vazamento entre clientes | RLS, FKs compostas, matriz de isolamento com ≥ 600 asserções no CI, suíte de isolamento da API | Baixo |
| Dado pessoal em log enviado à IA | Sanitização antes do LLM e do embedding; dados delimitados como não confiáveis; toggle para desligar o envio | Baixo |
| Transferência internacional (IA nos EUA) | Opção do Vertex AI em São Paulo; desligar o envio; sanitização antes | Médio, aceito pelo controlador ao escolher o provedor |
| Retenção além do necessário | Job diário de retenção (Storage e banco), com registro na auditoria | Baixo |
| Acesso indevido de funcionário | Papéis, MFA para ações administrativas, Trilha de auditoria imutável | Baixo |
| Identificação do titular pela Referência | Referência guardada só como HMAC com chave por Organização | Baixo |
| Indisponibilidade da IA | Modo só com as Regras, sem perder o diagnóstico básico | Baixo |

## Conclusão

O tratamento é necessário à finalidade e as medidas reduzem os riscos a um nível aceitável para o piloto. Pendências: revisão jurídica do DPA e conferência dos Advisors do Supabase antes do primeiro cliente (ver `docs/operations/pendencias.md`).
