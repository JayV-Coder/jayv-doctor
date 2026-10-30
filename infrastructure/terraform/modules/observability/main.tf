variable "project_id" {
  type = string
}

variable "api_domain" {
  type = string
}

# Logs de aplicação: 30 dias. Alertas (incluindo DLQ) vêm no ticket #34.
resource "google_logging_project_bucket_config" "default" {
  project        = var.project_id
  location       = "global"
  bucket_id      = "_Default"
  retention_days = 30
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
