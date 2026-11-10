locals {
  name_prefix = "aid"

  # Privilégio mínimo: o que cada serviço lê e publica é declarado aqui.
  workers = {
    # O Log bruto chega a 50 MB e é lido inteiro: 1 GiB de folga para o parse e a Sanitização.
    ingestion   = { secrets = ["supabase-db-url", "hmac-master-key", "supabase-service-role-key"], memory = "1Gi", timeout = "300s" }
    correlation = { secrets = ["supabase-db-url"], memory = "512Mi", timeout = "300s" }
    diagnosis   = { secrets = ["supabase-db-url", "anthropic-api-key", "voyage-api-key", "supabase-service-role-key", "smtp-url"], memory = "1Gi", timeout = "600s" }
    connectors  = { secrets = ["supabase-db-url"], memory = "512Mi", timeout = "600s" }
    # Relay da outbox: o único que publica nos tópicos, chamado pelo Cloud Scheduler.
    relay = { secrets = ["supabase-db-url"], memory = "256Mi", timeout = "60s" }
  }

  # ack_deadline >= timeout do worker: no push, o Pub/Sub reentrega ao fim do prazo, mesmo com o
  # worker ainda processando. 600 s é o máximo do Pub/Sub.
  topics = {
    "ingestion.raw"         = { worker = "ingestion", publishers = ["relay"], ack_deadline = 300 }
    "ingestion.normalized"  = { worker = "correlation", publishers = ["relay"], ack_deadline = 300 }
    "correlation.requested" = { worker = "correlation", publishers = ["relay"], ack_deadline = 300 }
    # Execução fechada vai para as Regras (ticket #18), no worker de diagnóstico.
    "rules.evaluate" = { worker = "diagnosis", publishers = ["relay"], ack_deadline = 600 }
    # Consumidos de verdade no #24 e nos alertas (v0.3); até lá o worker só confirma.
    "incident.opened"  = { worker = "diagnosis", publishers = ["relay"], ack_deadline = 600 }
    "incident.updated" = { worker = "diagnosis", publishers = ["relay"], ack_deadline = 600 }
    # Indexação de documentos da Base de conhecimento (#23).
    "knowledge.index"     = { worker = "diagnosis", publishers = ["relay"], ack_deadline = 600 }
    "diagnosis.requested" = { worker = "diagnosis", publishers = ["relay"], ack_deadline = 600 }
    # Diagnóstico publicado (#24): quem consome chega com os alertas (v0.3).
    "diagnosis.published" = { worker = "diagnosis", publishers = ["relay"], ack_deadline = 600 }
    # Avisos de Cota aos 80% e 100% (#31): e-mail para Owner e Admin.
    "usage.threshold"  = { worker = "diagnosis", publishers = ["relay"], ack_deadline = 600 }
    "report.requested" = { worker = "diagnosis", publishers = ["relay"], ack_deadline = 600 }
    "connector.sync"   = { worker = "connectors", publishers = ["relay"], ack_deadline = 600 }
    # Consultas de leitura do enriquecimento (#40): só o worker de Conectores lê credenciais.
    "enrichment.requested" = { worker = "connectors", publishers = ["relay"], ack_deadline = 600 }
  }

  # voyage-api-key: a busca da Base de conhecimento gera o embedding da pergunta (#23).
  api_secrets = ["supabase-db-url", "hmac-master-key", "smtp-url", "voyage-api-key"]

  secret_env = {
    "supabase-db-url"   = "SUPABASE_DB_URL"
    "anthropic-api-key" = "ANTHROPIC_API_KEY"
    # Embeddings da Base de conhecimento (Voyage, parceira da Anthropic), ticket #22.
    "voyage-api-key"  = "VOYAGE_API_KEY"
    "hmac-master-key" = "HMAC_MASTER_KEY"
    "smtp-url"        = "SMTP_URL"
    # Só o worker de ingestão: lê o Log bruto no Storage como job de plataforma.
    "supabase-service-role-key" = "SUPABASE_SERVICE_ROLE_KEY"
  }

  service_accounts = merge(
    { api = google_service_account.api.email },
    { for name, account in google_service_account.worker : name => account.email },
  )
}

data "google_project" "this" {
  project_id = var.project_id
}

module "project" {
  source     = "../modules/project"
  project_id = var.project_id
}

module "network" {
  source      = "../modules/network"
  name_prefix = local.name_prefix
  project_id  = var.project_id
  region      = var.region
  depends_on  = [module.project]
}

resource "google_artifact_registry_repository" "images" {
  project       = var.project_id
  location      = var.region
  repository_id = "aid"
  format        = "DOCKER"

  cleanup_policies {
    id     = "manter-20-recentes"
    action = "KEEP"
    most_recent_versions {
      keep_count = 20
    }
  }

  cleanup_policies {
    id     = "apagar-antigas"
    action = "DELETE"
    condition {
      older_than = "2592000s"
    }
  }

  depends_on = [module.project]
}

module "secrets" {
  source     = "../modules/secrets"
  project_id = var.project_id
  region     = var.region
  secret_ids = toset(keys(local.secret_env))
  accessors = merge(
    {
      for secret in local.api_secrets : "${secret}/api" => {
        secret = secret
        member = "serviceAccount:${google_service_account.api.email}"
      }
    },
    merge([
      for name, worker in local.workers : {
        for secret in worker.secrets : "${secret}/${name}" => {
          secret = secret
          member = "serviceAccount:${google_service_account.worker[name].email}"
        }
      }
    ]...),
  )
  depends_on = [module.project]
}

resource "google_service_account" "worker" {
  for_each     = local.workers
  project      = var.project_id
  account_id   = "${local.name_prefix}-worker-${each.key}"
  display_name = "Worker ${each.key}"
  depends_on   = [module.project]
}

module "api" {
  source                = "../modules/run-service"
  project_id            = var.project_id
  region                = var.region
  name                  = "api"
  service_account_email = google_service_account.api.email
  ingress               = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
  # O Load Balancer não apresenta token do IAM; a API valida o JWT do Supabase em cada rota.
  public_invoker      = true
  subnetwork          = module.network.subnetwork_id
  min_instances       = var.api_min_instances
  max_instances       = var.api_max_instances
  concurrency         = var.api_concurrency
  deletion_protection = var.environment == "prod"
  env = {
    SUPABASE_JWT_ISSUER = var.supabase_jwt_issuer
    SUPABASE_URL        = trimsuffix(var.supabase_jwt_issuer, "/auth/v1")
    # A web repassa o IP do navegador: balanceador do Cloud Run + web (Trilha de auditoria, #28).
    AID_TRUSTED_PROXY_HOPS   = "2"
    SUPABASE_PUBLISHABLE_KEY = var.supabase_publishable_key
    APP_URL                  = var.app_url
    # Liga os logs JSON ao trace (`logging.googleapis.com/trace`, #34).
    GCP_PROJECT_ID = var.project_id
    OTEL_ENABLED   = "true"
  }
  secret_env = { for secret in local.api_secrets : local.secret_env[secret] => secret }
  depends_on = [module.secrets]
}

resource "google_service_account" "api" {
  project      = var.project_id
  account_id   = "${local.name_prefix}-api"
  display_name = "API"
  depends_on   = [module.project]
}

# Traces e métricas da API: tenant.id como atributo, sem dado pessoal.
resource "google_project_iam_member" "api_telemetry" {
  for_each = toset(["roles/cloudtrace.agent", "roles/monitoring.metricWriter"])
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.api.email}"
}

module "workers" {
  source                = "../modules/run-service"
  for_each              = local.workers
  project_id            = var.project_id
  region                = var.region
  name                  = "worker-${each.key}"
  service_account_email = google_service_account.worker[each.key].email
  # O relay aceita tráfego de fora da VPC para os operadores abrirem o /admin/health com
  # `gcloud run services proxy` (#34); continua só com IAM (sem invocação pública).
  ingress             = each.key == "relay" ? "INGRESS_TRAFFIC_ALL" : "INGRESS_TRAFFIC_INTERNAL_ONLY"
  public_invoker      = false
  subnetwork          = module.network.subnetwork_id
  memory              = each.value.memory
  timeout             = each.value.timeout
  max_instances       = var.worker_max_instances
  concurrency         = var.worker_concurrency
  deletion_protection = var.environment == "prod"
  env = merge(
    {
      WORKER_NAME    = each.key
      SUPABASE_URL   = trimsuffix(var.supabase_jwt_issuer, "/auth/v1")
      GCP_PROJECT_ID = var.project_id
      OTEL_ENABLED   = "true"
    },
    # O backup do Storage (#33) roda no worker de diagnóstico, que tem a chave do Storage.
    each.key == "diagnosis" ? { BACKUP_BUCKET = google_storage_bucket.storage_backup.name } : {},
  )
  secret_env = { for secret in each.value.secrets : local.secret_env[secret] => secret }
  depends_on = [module.secrets]
}

# Identidade que o Pub/Sub apresenta aos workers.
resource "google_service_account" "pubsub_push" {
  project      = var.project_id
  account_id   = "${local.name_prefix}-pubsub-push"
  display_name = "Push autenticado do Pub/Sub"
  depends_on   = [module.project]
}

resource "google_cloud_run_v2_service_iam_member" "pubsub_invoker" {
  # Só quem tem assinatura: o relay é chamado pelo Cloud Scheduler, não pelo Pub/Sub.
  for_each = toset([for topic in local.topics : topic.worker])
  project  = var.project_id
  location = var.region
  name     = module.workers[each.value].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.pubsub_push.email}"
}

resource "google_service_account_iam_member" "pubsub_token_creator" {
  service_account_id = google_service_account.pubsub_push.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:service-${data.google_project.this.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

module "topics" {
  source                     = "../modules/pubsub-topic"
  for_each                   = local.topics
  project_id                 = var.project_id
  project_number             = data.google_project.this.number
  region                     = var.region
  name                       = each.key
  push_endpoint              = "${module.workers[each.value.worker].uri}/pubsub"
  push_audience              = module.workers[each.value.worker].uri
  push_service_account_email = google_service_account.pubsub_push.email
  ack_deadline_seconds       = each.value.ack_deadline
  publishers = {
    for publisher in each.value.publishers : publisher => "serviceAccount:${local.service_accounts[publisher]}"
  }
  depends_on = [module.project]
}

module "edge" {
  source                = "../modules/public-lb"
  name_prefix           = local.name_prefix
  project_id            = var.project_id
  region                = var.region
  domain                = var.api_domain
  cloud_run_service     = module.api.name
  rate_limit_per_minute = var.rate_limit_per_minute
}

module "deploy" {
  source             = "../modules/github-deploy"
  project_id         = var.project_id
  region             = var.region
  repository_id      = google_artifact_registry_repository.images.repository_id
  github_repository  = var.github_repository
  github_environment = var.github_environment
  services = merge(
    { api = module.api.name },
    { for name, worker in module.workers : name => worker.name },
  )
  runtime_service_accounts = local.service_accounts
  depends_on               = [module.project]
}

module "observability" {
  source             = "../modules/observability"
  project_id         = var.project_id
  region             = var.region
  api_domain         = var.api_domain
  alert_emails       = var.alert_emails
  oncall_webhook_url = var.oncall_webhook_url
  runbook_base_url   = "https://github.com/${var.github_repository}/blob/main"
  depends_on         = [module.project]
}

# Traces e métricas dos workers (#34): o mesmo da API.
resource "google_project_iam_member" "worker_telemetry" {
  for_each = { for pair in setproduct(keys(local.workers), ["roles/cloudtrace.agent", "roles/monitoring.metricWriter"]) : "${pair[0]}/${pair[1]}" => pair }
  project  = var.project_id
  role     = each.value[1]
  member   = "serviceAccount:${google_service_account.worker[each.value[0]].email}"
}

# Medidas da plataforma no Cloud Monitoring a cada minuto, pelo worker de diagnóstico, que tem a
# chave da Metrics API do Supabase.
resource "google_cloud_scheduler_job" "platform_metrics" {
  project          = var.project_id
  region           = var.region
  name             = "${local.name_prefix}-platform-metrics"
  schedule         = "* * * * *"
  time_zone        = "Etc/UTC"
  attempt_deadline = "60s"

  http_target {
    http_method = "POST"
    uri         = "${module.workers["diagnosis"].uri}/platform/metrics"

    oidc_token {
      service_account_email = google_service_account.scheduler.email
      audience              = module.workers["diagnosis"].uri
    }
  }

  depends_on = [module.project]
}

# `/admin/health` dos operadores: no relay, interno e só com o IAM; tenant nenhum chega lá.
resource "google_cloud_run_v2_service_iam_member" "operators" {
  for_each = toset(var.platform_operators)
  project  = var.project_id
  location = var.region
  name     = module.workers["relay"].name
  role     = "roles/run.invoker"
  member   = each.value
}

# A outbox é drenada a cada minuto: o lag máximo de uma mensagem é ~1 min mais a rodada.
resource "google_service_account" "scheduler" {
  project      = var.project_id
  account_id   = "${local.name_prefix}-scheduler"
  display_name = "Cloud Scheduler"
  depends_on   = [module.project]
}

resource "google_cloud_run_v2_service_iam_member" "scheduler_invoker" {
  project  = var.project_id
  location = var.region
  name     = module.workers["relay"].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler.email}"
}

resource "google_cloud_run_v2_service_iam_member" "scheduler_invoker_connectors" {
  project  = var.project_id
  location = var.region
  name     = module.workers["connectors"].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler.email}"
}

# Agendador dos Conectores: enfileira connector.sync para os vencidos (o pg_cron é do jayv-coder).
resource "google_cloud_scheduler_job" "connector_schedule" {
  project          = var.project_id
  region           = var.region
  name             = "${local.name_prefix}-connector-schedule"
  schedule         = "* * * * *"
  time_zone        = "Etc/UTC"
  attempt_deadline = "60s"

  http_target {
    http_method = "POST"
    uri         = "${module.workers["connectors"].uri}/schedule"

    oidc_token {
      service_account_email = google_service_account.scheduler.email
      audience              = module.workers["connectors"].uri
    }
  }

  depends_on = [module.project]
}

resource "google_cloud_run_v2_service_iam_member" "scheduler_invoker_correlation" {
  project  = var.project_id
  location = var.region
  name     = module.workers["correlation"].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler.email}"
}

# Fechamento das Execuções paradas há 5 min: status final e rules.evaluate na outbox.
resource "google_cloud_scheduler_job" "correlation_close" {
  project          = var.project_id
  region           = var.region
  name             = "${local.name_prefix}-correlation-close"
  schedule         = "* * * * *"
  time_zone        = "Etc/UTC"
  attempt_deadline = "60s"

  http_target {
    http_method = "POST"
    uri         = "${module.workers["correlation"].uri}/close"

    oidc_token {
      service_account_email = google_service_account.scheduler.email
      audience              = module.workers["correlation"].uri
    }
  }

  depends_on = [module.project]
}

resource "google_cloud_run_v2_service_iam_member" "scheduler_invoker_diagnosis" {
  project  = var.project_id
  location = var.region
  name     = module.workers["diagnosis"].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler.email}"
}

# Reindexação da Base de conhecimento quando o provedor de IA de uma Organização muda (#23).
resource "google_cloud_scheduler_job" "knowledge_reindex" {
  project          = var.project_id
  region           = var.region
  name             = "${local.name_prefix}-knowledge-reindex"
  schedule         = "17 * * * *"
  time_zone        = "Etc/UTC"
  attempt_deadline = "120s"

  http_target {
    http_method = "POST"
    uri         = "${module.workers["diagnosis"].uri}/knowledge/reindex"

    oidc_token {
      service_account_email = google_service_account.scheduler.email
      audience              = module.workers["diagnosis"].uri
    }
  }

  depends_on = [module.project]
}

# Agregado do Dashboard (ticket #21): recalcula as horas tocadas desde a última rodada.
resource "google_cloud_scheduler_job" "dashboard_stats" {
  project          = var.project_id
  region           = var.region
  name             = "${local.name_prefix}-dashboard-stats"
  schedule         = "*/10 * * * *"
  time_zone        = "Etc/UTC"
  attempt_deadline = "120s"

  http_target {
    http_method = "POST"
    uri         = "${module.workers["correlation"].uri}/stats"

    oidc_token {
      service_account_email = google_service_account.scheduler.email
      audience              = module.workers["correlation"].uri
    }
  }

  depends_on = [module.project]
}

# Retenção e exclusão (#29): todo dia às 03:00 BRT (06:00 UTC), no worker de diagnóstico, que
# tem a chave do Storage. O pg_cron do projeto é do jayv-coder (ADR-0009).
resource "google_cloud_scheduler_job" "retention" {
  project          = var.project_id
  region           = var.region
  name             = "${local.name_prefix}-retention"
  schedule         = "0 6 * * *"
  time_zone        = "Etc/UTC"
  attempt_deadline = "1800s"

  http_target {
    http_method = "POST"
    uri         = "${module.workers["diagnosis"].uri}/retention/run"

    oidc_token {
      service_account_email = google_service_account.scheduler.email
      audience              = module.workers["diagnosis"].uri
    }
  }

  depends_on = [module.project]
}

# Enriquecimento (#40): a cada 5 min, consulta sem resposta vira `failed` e o Diagnóstico segue.
resource "google_cloud_scheduler_job" "enrichment_expire" {
  project          = var.project_id
  region           = var.region
  name             = "${local.name_prefix}-enrichment-expire"
  schedule         = "*/5 * * * *"
  time_zone        = "Etc/UTC"
  attempt_deadline = "120s"

  http_target {
    http_method = "POST"
    uri         = "${module.workers["diagnosis"].uri}/enrichment/expire"

    oidc_token {
      service_account_email = google_service_account.scheduler.email
      audience              = module.workers["diagnosis"].uri
    }
  }

  depends_on = [module.project]
}

# Trilha de auditoria (#28): login e MFA do Supabase Auth e as partições dos próximos meses.
resource "google_cloud_scheduler_job" "audit_auth_events" {
  project          = var.project_id
  region           = var.region
  name             = "${local.name_prefix}-audit-auth-events"
  schedule         = "40 3 * * *"
  time_zone        = "Etc/UTC"
  attempt_deadline = "300s"

  http_target {
    http_method = "POST"
    uri         = "${module.workers["correlation"].uri}/audit/auth-events"

    oidc_token {
      service_account_email = google_service_account.scheduler.email
      audience              = module.workers["correlation"].uri
    }
  }

  depends_on = [module.project]
}

resource "google_cloud_scheduler_job" "outbox_relay" {
  project          = var.project_id
  region           = var.region
  name             = "${local.name_prefix}-outbox-relay"
  schedule         = "* * * * *"
  time_zone        = "Etc/UTC"
  attempt_deadline = "60s"

  http_target {
    http_method = "POST"
    uri         = "${module.workers["relay"].uri}/relay"

    oidc_token {
      service_account_email = google_service_account.scheduler.email
      audience              = module.workers["relay"].uri
    }
  }

  depends_on = [module.project]
}

# Backup dos arquivos do Storage (#33): espelho dos buckets do Doctor, no Brasil. Com
# versionamento, o que a origem apaga (retenção, LGPD, exclusão total) sai do espelho e fica 7
# dias como versão antiga; depois some de vez. Sem soft delete do GCS, para não estender isso.
resource "google_storage_bucket" "storage_backup" {
  project                     = var.project_id
  name                        = "${var.project_id}-storage-backup"
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  versioning {
    enabled = true
  }

  soft_delete_policy {
    retention_duration_seconds = 0
  }

  lifecycle_rule {
    condition {
      days_since_noncurrent_time = 7
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [module.project]
}

# Só o worker de diagnóstico escreve; ninguém mais da stack lê.
resource "google_storage_bucket_iam_member" "storage_backup_writer" {
  bucket = google_storage_bucket.storage_backup.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.worker["diagnosis"].email}"
}

resource "google_cloud_scheduler_job" "storage_backup" {
  project = var.project_id
  region  = var.region
  name    = "${local.name_prefix}-storage-backup"
  # De hora em hora (RPO dos arquivos ≤ 1 h); cada rodada cabe no timeout do worker e a que
  # não termina continua na seguinte.
  schedule         = "20 * * * *"
  time_zone        = "Etc/UTC"
  attempt_deadline = "600s"

  http_target {
    http_method = "POST"
    uri         = "${module.workers["diagnosis"].uri}/backup/storage"

    oidc_token {
      service_account_email = google_service_account.scheduler.email
      audience              = module.workers["diagnosis"].uri
    }
  }

  depends_on = [module.project]
}

# Conexões possíveis no pior caso (todas as instâncias cheias) cabem na fatia do Supavisor.
check "conexoes_cabem_no_supavisor" {
  assert {
    condition = (
      var.api_max_instances * var.api_concurrency
      + length(local.workers) * var.worker_max_instances * var.worker_concurrency
    ) <= var.supavisor_client_budget
    error_message = "Instâncias × concorrência passam da fatia do Supavisor reservada ao Doctor."
  }
}
