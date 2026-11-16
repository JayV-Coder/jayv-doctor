# Rotação de segredos

Os segredos ficam no Secret Manager de cada ambiente (`southamerica-east1`), e cada serviço lê só os seus (teste `segredos_ficam_no_brasil_e_cada_servico_le_so_o_seu` no Terraform). Nenhum valor vai para chat, ticket ou log.

**Regra geral:** adicione a versão nova, publique uma revisão do serviço que a lê (o Cloud Run lê o segredo ao subir) e só depois desabilite a antiga:

```bash
printf %s "$NOVO" | gcloud secrets versions add <segredo> --project <projeto> --data-file=-
gcloud run services update <serviço> --region southamerica-east1 --project <projeto> --update-labels=rotacao=$(date +%Y%m%d)
gcloud secrets versions disable <versão-antiga> --secret <segredo> --project <projeto>
```

| Segredo | Quem lê | Rotação | Cuidado |
|---|---|---|---|
| `supabase-db-url` | API e workers | a cada 90 dias, ou já se vazar | a senha do Postgres é do projeto compartilhado com o jayv-coder (ADR-0009): troque em janela combinada |
| `supabase-service-role-key` | workers de ingestão e diagnóstico | se vazar | é do projeto inteiro: a rotação no Supabase afeta o jayv-coder |
| `anthropic-api-key`, `voyage-api-key` | worker de diagnóstico | a cada 90 dias | crie a chave nova no console do provedor antes de revogar a antiga |
| `smtp-url` | API e worker de diagnóstico | com a senha do provedor de e-mail | teste com um convite |
| `supabase-access-token` | worker `notifier` (SSO, #48) | a cada 90 dias, ou já se vazar | token pessoal da Management API: dá poder sobre o projeto inteiro, inclusive o jayv-coder. Crie o novo antes de revogar o antigo e confira com um `PUT /api/v1/sso` de teste |
| `hmac-master-key` | API e worker de ingestão | **não rotacione sem plano** | a Referência de negócio é HMAC dela: trocar a chave faz as buscas por pedido antigo pararem de achar. Rotação exige reprocessar as Referências (ticket próprio) |
| Tokens de ingestão (`aid_ing_…`) | sistemas do cliente | pelo cliente, na tela | revogar é imediato; crie o novo antes |
| Chaves dos Conectores | Vault do Supabase | pelo cliente, editando o Conector | a antiga sai do Vault na edição |

Depois de uma rotação, confira o `/admin/health` e os alertas: credencial errada aparece como 5xx na API, como lote de ingestão em falha ou como `supabase_metrics_up = 0`.
