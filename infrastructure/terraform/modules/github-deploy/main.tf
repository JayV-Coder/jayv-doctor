variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "repository_id" {
  type = string
}

variable "github_repository" {
  type = string
}

variable "github_environment" {
  type = string
}

variable "services" {
  description = "Chave estável => nome do serviço Cloud Run que o deploy pode atualizar."
  type        = map(string)
}

variable "runtime_service_accounts" {
  description = "Chave estável => e-mail da service account de runtime."
  type        = map(string)
}

resource "google_iam_workload_identity_pool" "github" {
  project                   = var.project_id
  workload_identity_pool_id = "github"
}

resource "google_iam_workload_identity_pool_provider" "actions" {
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "actions"
  # Qualquer repositório do GitHub tem token válido do mesmo emissor: a condição é o que restringe.
  attribute_condition = "assertion.repository == \"${var.github_repository}\" && assertion.environment == \"${var.github_environment}\""

  attribute_mapping = {
    "google.subject"        = "assertion.sub"
    "attribute.repository"  = "assertion.repository"
    "attribute.environment" = "assertion.environment"
  }

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account" "deployer" {
  project      = var.project_id
  account_id   = "aid-deployer"
  display_name = "Deploy pelo GitHub Actions"
}

resource "google_service_account_iam_member" "github_impersonates_deployer" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repository}"
}

resource "google_artifact_registry_repository_iam_member" "writer" {
  project    = var.project_id
  location   = var.region
  repository = var.repository_id
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_cloud_run_v2_service_iam_member" "developer" {
  for_each = var.services
  project  = var.project_id
  location = var.region
  name     = each.value
  role     = "roles/run.developer"
  member   = "serviceAccount:${google_service_account.deployer.email}"
}

# Os serviços usam Direct VPC egress: a validação da revisão lê a sub-rede.
resource "google_project_iam_member" "network_viewer" {
  project = var.project_id
  role    = "roles/compute.networkViewer"
  member  = "serviceAccount:${google_service_account.deployer.email}"
}

# Publicar uma revisão exige agir como a service account de runtime dela.
resource "google_service_account_iam_member" "acts_as_runtime" {
  for_each           = var.runtime_service_accounts
  service_account_id = "projects/${var.project_id}/serviceAccounts/${each.value}"
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deployer.email}"
}

output "workload_identity_provider" {
  value = google_iam_workload_identity_pool_provider.actions.name
}

output "service_account_email" {
  value = google_service_account.deployer.email
}

output "attribute_condition" {
  value = google_iam_workload_identity_pool_provider.actions.attribute_condition
}
