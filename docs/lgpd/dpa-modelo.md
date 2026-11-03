# Modelo de acordo de tratamento de dados (DPA)

> Modelo para o piloto. Os trechos entre colchetes são preenchidos por contrato.

1. **Partes e papéis.** [Cliente] é o controlador; [Empresa do Doctor] é o operador dos dados tratados no Integration AI Doctor (ver `papeis.md`).
2. **Objeto e finalidade.** Monitorar e diagnosticar falhas das integrações do controlador (SAP, Salesforce, Google Cloud), a partir dos logs que o controlador envia ou autoriza coletar. Nenhum outro uso: os dados não treinam modelos nem servem a outro cliente.
3. **Instruções.** O operador segue as instruções registradas no produto (retenção, envio ao LLM, exclusão) e as enviadas por escrito pelo controlador.
4. **Confidencialidade.** Só pessoas do operador com necessidade, sob dever de sigilo, acessam dados do controlador, e cada acesso administrativo é auditado.
5. **Segurança.** Isolamento entre clientes por RLS e chaves compostas, verificado no CI a cada mudança; criptografia em trânsito e em repouso; credenciais no Vault; MFA obrigatório para Owner e Admin; Sanitização antes de gravar e antes da IA; Trilha de auditoria imutável por 365 dias.
6. **Subprocessadores.** Os listados no produto. O operador avisa o controlador com [30] dias de antecedência sobre um subprocessador novo, e o controlador pode se opor.
7. **Transferência internacional.** Ver `transferencia-internacional.md`. O controlador pode escolher o Google Vertex AI em São Paulo ou desligar o envio ao LLM.
8. **Direitos dos titulares.** O operador dá ao controlador os meios de localizar e apagar os Eventos de um titular (Mais › Direitos do titular) e responde a pedidos do controlador em até [5] dias úteis.
9. **Incidentes.** O operador comunica o controlador em até [24 horas] depois de confirmar um incidente que envolva os dados dele, com o que se sabe até ali (ver `resposta-a-incidentes.md`).
10. **Retenção e término.** Os dados seguem a retenção configurada (padrão: Logs brutos 30 dias, Eventos 90, Incidentes e Diagnósticos 180, auditoria 365, Base de conhecimento até o controlador excluir). No término, a exclusão total apaga banco, arquivos e credenciais em até 7 dias depois do pedido e emite um comprovante.
11. **Auditoria.** O controlador pode pedir os relatórios de isolamento e o checklist de segurança (`docs/security/`) e uma auditoria por terceiro independente, [uma vez por ano].
