# Infraestrutura GCP

Terraform em `infrastructure/terraform`: `stack/` é a composição única e `environments/` guarda o que muda por ambiente. `make tf:check` roda fmt, validate, tflint e os testes, sem credenciais.

## Primeiro uso de um ambiente

Exemplo com staging. Requer um projeto com billing e `gcloud auth login` + `gcloud auth application-default login`.

1. Ajuste `environments/staging.tfvars` e `environments/staging.backend.hcl`.
2. Crie o bucket do state (versionado, no Brasil):

   ```bash
   gcloud storage buckets create gs://<bucket> --project <projeto> \
     --location southamerica-east1 --uniform-bucket-level-access
   gcloud storage buckets update gs://<bucket> --versioning
   ```

3. Crie primeiro os segredos: o Cloud Run recusa revisão que aponta para segredo sem versão.

   ```bash
   cd infrastructure/terraform/stack
   terraform init -reconfigure -backend-config=../environments/staging.backend.hcl
   terraform apply -var-file=../environments/staging.tfvars -target=module.secrets
   ```

4. Grave os valores. Eles nunca passam pelo Terraform, então não vão para o state:

   ```bash
   printf %s "$VALOR" | gcloud secrets versions add supabase-db-url --project <projeto> --data-file=-
   ```

   Repita para `anthropic-api-key` e `hmac-master-key`. Se os segredos existirem sem valor, o passo 5 falha.

5. `make tf:apply ENV=staging`.
6. Aponte o DNS de `api_domain` para a saída `api_ip`. O certificado gerenciado só ativa depois disso e pode levar até 1 h.
7. Libere a saída `egress_ip` nas restrições de rede do Supabase, se estiverem ligadas.
8. Crie o GitHub Environment `staging` com as variáveis da saída `github_variables`. Em `production`, adicione revisores obrigatórios: é isso que dá a aprovação manual.
9. Defina a variável de repositório `DEPLOY_ENABLED=true`.
10. Rode `make tf:plan ENV=staging`: o resultado esperado é nenhum diff.

## Deploy

Quando o CI de um merge na `main` passa, `deploy.yml` roda: staging publica a imagem do commit e production espera aprovação. O Terraform ignora a imagem dos serviços, então deploy não gera diff. Como o Artifact Registry é por projeto, cada ambiente constrói a própria imagem do mesmo commit.

## Mensagens na DLQ

Cada tópico tem `<tópico>.dlq` e a assinatura `<tópico>.dlq.pull`, com retenção de 7 dias. Para inspecionar sem consumir:

```bash
gcloud pubsub subscriptions pull ingestion.raw.dlq.pull --project <projeto> --limit 5
```

Enquanto um tópico não tiver handler, o worker responde `501` e a mensagem vai para a DLQ.

## Custos fixos

Além do uso, cada ambiente paga Load Balancer, Cloud NAT com IP estático e Cloud Armor, mesmo sem tráfego. `terraform destroy` não é um jeito de economizar: o id do pool de Workload Identity fica reservado por 30 dias, o que quebra o próximo apply, e os valores dos segredos se perdem.
