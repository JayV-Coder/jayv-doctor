locals {
  name_prefix = "aid"

  # Privilégio mínimo: o que cada serviço lê e publica é declarado aqui.
  workers = {
    ingestion   = { secrets = ["supabase-db-url", "hmac-master-key"], memory = "512Mi", timeout = "300s" }
    correlation = { secrets = ["supabase-db-url", "hmac-master-key"], memory = "512Mi", timeout = "300s" }
    diagnosis   = { secrets = ["supabase-db-url", "anthropic-api-key"], memory = "1Gi", timeout = "900s" }
    connectors  = { secrets = ["supabase-db-url"], memory = "512Mi", timeout = "600s" }
  }

  topics = {
    "ingestion.raw"         = { worker = "ingestion", publishers = ["api", "connectors"], ack_deadline = 60 }
    "ingestion.normalized"  = { worker = "correlation", publishers = ["ingestion"], ack_deadline = 60 }
    "correlation.requested" = { worker = "correlation", publishers = ["ingestion"], ack_deadline = 60 }
    "diagnosis.requested"   = { worker = "diagnosis", publishers = ["api", "correlation"], ack_deadline = 600 }
    "connector.sync"        = { worker = "connectors", publishers = ["api"], ack_deadline = 600 }
  }

  secret_env = {
    "supabase-db-url"   = "SUPABASE_DB_URL"
    "anthropic-api-key" = "ANTHROPIC_API_KEY"
    "hmac-master-key"   = "HMAC_MASTER_KEY"
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
    { "supabase-db-url/api" = { secret = "supabase-db-url", member = "serviceAccount:${google_service_account.api.email}" } },
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
  deletion_protection = var.environment == "prod"
  env                 = { SUPABASE_JWT_ISSUER = var.supabase_jwt_issuer }
  secret_env          = { SUPABASE_DB_URL = "supabase-db-url" }
  depends_on          = [module.secrets]
}

resource "google_service_account" "api" {
  project      = var.project_id
  account_id   = "${local.name_prefix}-api"
  display_name = "API"
  depends_on   = [module.project]
}

module "workers" {
  source                = "../modules/run-service"
  for_each              = local.workers
  project_id            = var.project_id
  region                = var.region
  name                  = "worker-${each.key}"
  service_account_email = google_service_account.worker[each.key].email
  ingress               = "INGRESS_TRAFFIC_INTERNAL_ONLY"
  public_invoker        = false
  subnetwork            = module.network.subnetwork_id
  memory                = each.value.memory
  timeout               = each.value.timeout
  deletion_protection   = var.environment == "prod"
  env                   = { WORKER_NAME = each.key }
  secret_env            = { for secret in each.value.secrets : local.secret_env[secret] => secret }
  depends_on            = [module.secrets]
}

# Identidade que o Pub/Sub apresenta aos workers.
resource "google_service_account" "pubsub_push" {
  project      = var.project_id
  account_id   = "${local.name_prefix}-pubsub-push"
  display_name = "Push autenticado do Pub/Sub"
  depends_on   = [module.project]
}

resource "google_cloud_run_v2_service_iam_member" "pubsub_invoker" {
  for_each = local.workers
  project  = var.project_id
  location = var.region
  name     = module.workers[each.key].name
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
  source     = "../modules/observability"
  project_id = var.project_id
  api_domain = var.api_domain
  depends_on = [module.project]
}
