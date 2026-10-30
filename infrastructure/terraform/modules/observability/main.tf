variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "api_domain" {
  type = string
}

# O bucket _Default é global e não pode mudar de região: logs dos serviços têm bucket próprio no
# Brasil e saem do _Default. Alertas (incluindo DLQ) vêm no ticket #34.
locals {
  run_logs = "resource.type=\"cloud_run_revision\""
}

resource "google_logging_project_bucket_config" "services" {
  project        = var.project_id
  location       = var.region
  bucket_id      = "aid-services"
  retention_days = 30
}

resource "google_logging_project_sink" "services" {
  project     = var.project_id
  name        = "aid-services"
  destination = "logging.googleapis.com/${google_logging_project_bucket_config.services.id}"
  filter      = local.run_logs
}

resource "google_logging_project_exclusion" "services_from_default" {
  project = var.project_id
  name    = "aid-services-fora-do-default"
  filter  = local.run_logs
}

resource "google_monitoring_uptime_check_config" "api" {
  project      = var.project_id
  display_name = "API"
  timeout      = "10s"
  period       = "300s"

  http_check {
    path    = "/api/v1/openapi.json"
    port    = 443
    use_ssl = true
  }

  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.project_id
      host       = var.api_domain
    }
  }
}

output "log_location" {
  value = google_logging_project_bucket_config.services.location
}
