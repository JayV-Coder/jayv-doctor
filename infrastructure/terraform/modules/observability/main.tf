variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "api_domain" {
  type = string
}

variable "alert_emails" {
  description = "E-mails que recebem os alertas da plataforma."
  type        = list(string)
  default     = []
}

variable "oncall_webhook_url" {
  description = "Webhook do canal de plantão (vazio: só e-mail)."
  type        = string
  default     = ""
  sensitive   = true
}

variable "runbook_base_url" {
  description = "Onde os runbooks são lidos (o repositório, na main)."
  type        = string
}

# O bucket _Default é global e não pode mudar de região: logs dos serviços têm bucket próprio no
# Brasil e saem do _Default.
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

# Ticket #34: métricas da plataforma (gravadas a cada minuto pelo worker de diagnóstico), alertas
# com runbook e o dashboard operacional.
locals {
  custom_metrics = {
    outbox_lag_seconds        = "Idade da mensagem mais antiga da outbox sem publicar (s)"
    outbox_pending            = "Mensagens da outbox a publicar"
    outbox_stuck              = "Mensagens da outbox recusadas 10 vezes"
    ingestion_lag_seconds     = "Idade do lote de ingestão mais antigo na fila (s)"
    ingestion_batches_pending = "Lotes de ingestão na fila"
    connectors_failing        = "Conectores em failing"
    sync_p95_seconds_1h       = "Duração p95 das Sincronizações na última hora (s)"
    diagnoses_queued          = "Diagnósticos na fila"
    diagnosis_queue_seconds   = "Idade do Diagnóstico mais antigo na fila (s)"
    diagnosis_p95_seconds_1h  = "Duração p95 dos Diagnósticos na última hora (s)"
    llm_error_rate_1h         = "Taxa de falha do LLM na última hora (0 a 1)"
    llm_tokens_1h             = "Tokens do LLM na última hora"
    db_connections            = "Conexões no Postgres"
    supabase_cpu_utilization  = "CPU do Supabase (0 a 1)"
    supabase_disk_utilization = "Disco do Supabase (0 a 1)"
    supabase_metrics_up       = "Metrics API do Supabase respondendo (1 ou 0)"
  }

  custom = "resource.type=\"global\" AND metric.type=\"custom.googleapis.com/aid/%s\""

  # Limites numa fonte só, a mesma do `/admin/health` (aid_observability/limits.json).
  limits = jsondecode(file("${path.module}/../../../../packages/observability/src/aid_observability/limits.json"))

  threshold_alerts = merge(
    {
      for metric, rule in local.limits : metric => {
        name     = rule.name
        filter   = format(local.custom, metric)
        value    = rule.limit
        duration = rule.duration
        runbook  = rule.runbook
      }
    },
    {
      dlq = {
        name     = "DLQ com mensagens"
        filter   = "resource.type=\"pubsub_subscription\" AND metric.type=\"pubsub.googleapis.com/subscription/num_undelivered_messages\" AND resource.label.subscription_id=monitoring.regex.full_match(\".*\\\\.dlq\\\\.pull\")"
        value    = 0
        duration = "300s"
        runbook  = "dlq.md"
      }
      workers_stopped = {
        name     = "Workers sem processar por 10 min"
        filter   = "resource.type=\"pubsub_subscription\" AND metric.type=\"pubsub.googleapis.com/subscription/oldest_unacked_message_age\" AND resource.label.subscription_id=monitoring.regex.full_match(\".*\\\\.push\")"
        value    = 600
        duration = "60s"
        runbook  = "workers-parados.md"
      }
    },
  )

  channels = concat(
    [for channel in google_monitoring_notification_channel.email : channel.id],
    [for channel in google_monitoring_notification_channel.oncall : channel.id],
  )
}

resource "google_monitoring_metric_descriptor" "custom" {
  for_each     = local.custom_metrics
  project      = var.project_id
  type         = "custom.googleapis.com/aid/${each.key}"
  display_name = each.value
  description  = each.value
  metric_kind  = "GAUGE"
  value_type   = "DOUBLE"
}

resource "google_monitoring_notification_channel" "email" {
  for_each     = toset(var.alert_emails)
  project      = var.project_id
  display_name = "Plantão (e-mail) ${each.value}"
  type         = "email"
  labels       = { email_address = each.value }
}

resource "google_monitoring_notification_channel" "oncall" {
  for_each     = nonsensitive(var.oncall_webhook_url) == "" ? toset([]) : toset(["oncall"])
  project      = var.project_id
  display_name = "Canal de plantão"
  type         = "webhook_tokenauth"
  labels       = { url = var.oncall_webhook_url }
}

resource "google_monitoring_alert_policy" "threshold" {
  for_each              = local.threshold_alerts
  project               = var.project_id
  display_name          = each.value.name
  combiner              = "OR"
  notification_channels = local.channels

  conditions {
    display_name = each.value.name
    condition_threshold {
      filter          = each.value.filter
      comparison      = "COMPARISON_GT"
      threshold_value = each.value.value
      duration        = each.value.duration
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MAX"
      }
    }
  }

  documentation {
    content   = "Runbook: ${var.runbook_base_url}/docs/operations/runbooks/${each.value.runbook}"
    mime_type = "text/markdown"
  }

  alert_strategy {
    auto_close = "1800s"
  }

  depends_on = [google_monitoring_metric_descriptor.custom]
}

# Sem dado nenhum alerta de limite dispara: o job de métricas parado silenciaria a outbox, o LLM
# e a CPU. Este avisa quando as medidas da plataforma deixam de chegar.
resource "google_monitoring_alert_policy" "metrics_absent" {
  project               = var.project_id
  display_name          = "Medidas da plataforma sem chegar há 10 min"
  combiner              = "OR"
  notification_channels = local.channels

  conditions {
    display_name = "outbox_lag_seconds ausente"
    condition_absent {
      filter   = format(local.custom, "outbox_lag_seconds")
      duration = "600s"
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MAX"
      }
    }
  }

  conditions {
    display_name = "Metrics API do Supabase sem responder"
    condition_threshold {
      filter          = format(local.custom, "supabase_metrics_up")
      comparison      = "COMPARISON_LT"
      threshold_value = 1
      duration        = "900s"
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MAX"
      }
    }
  }

  documentation {
    content   = "Runbook: ${var.runbook_base_url}/docs/operations/runbooks/metricas-ausentes.md"
    mime_type = "text/markdown"
  }

  alert_strategy {
    auto_close = "1800s"
  }

  depends_on = [google_monitoring_metric_descriptor.custom]
}

# 5xx da API sobre o total, em PromQL (a razão não cabe num filtro de limite).
resource "google_monitoring_alert_policy" "api_errors" {
  project               = var.project_id
  display_name          = "API com 5xx acima de 1%"
  combiner              = "OR"
  notification_channels = local.channels

  conditions {
    display_name = "API com 5xx acima de 1%"
    condition_prometheus_query_language {
      query               = "sum(rate(run_googleapis_com:request_count{monitored_resource=\"cloud_run_revision\",service_name=\"api\",response_code_class=\"5xx\"}[5m])) / sum(rate(run_googleapis_com:request_count{monitored_resource=\"cloud_run_revision\",service_name=\"api\"}[5m])) > 0.01"
      duration            = "300s"
      evaluation_interval = "60s"
    }
  }

  documentation {
    content   = "Runbook: ${var.runbook_base_url}/docs/operations/runbooks/api-5xx.md"
    mime_type = "text/markdown"
  }

  alert_strategy {
    auto_close = "1800s"
  }
}

resource "google_monitoring_dashboard" "platform" {
  project = var.project_id
  dashboard_json = jsonencode({
    displayName = "Integration AI Doctor · plataforma"
    mosaicLayout = {
      columns = 12
      tiles = [
        for index, tile in [
          { title = "Lag da outbox (s)", filter = format(local.custom, "outbox_lag_seconds") },
          { title = "Mensagens na DLQ", filter = local.threshold_alerts.dlq.filter },
          { title = "Requisições da API por classe de resposta", filter = "resource.type=\"cloud_run_revision\" AND resource.label.service_name=\"api\" AND metric.type=\"run.googleapis.com/request_count\"" },
          { title = "Latência da API", filter = "resource.type=\"cloud_run_revision\" AND resource.label.service_name=\"api\" AND metric.type=\"run.googleapis.com/request_latencies\"" },
          { title = "Mensagem mais antiga sem ack por assinatura (s)", filter = local.threshold_alerts.workers_stopped.filter },
          { title = "Lag da ingestão (s)", filter = format(local.custom, "ingestion_lag_seconds") },
          { title = "Sincronizações p95 (s)", filter = format(local.custom, "sync_p95_seconds_1h") },
          { title = "Conectores em failing", filter = format(local.custom, "connectors_failing") },
          { title = "Diagnósticos p95 (s)", filter = format(local.custom, "diagnosis_p95_seconds_1h") },
          { title = "Erro do LLM (0 a 1)", filter = format(local.custom, "llm_error_rate_1h") },
          { title = "Tokens do LLM por hora", filter = format(local.custom, "llm_tokens_1h") },
          { title = "Conexões no Postgres", filter = format(local.custom, "db_connections") },
          { title = "CPU do Supabase", filter = format(local.custom, "supabase_cpu_utilization") },
          { title = "Disco do Supabase", filter = format(local.custom, "supabase_disk_utilization") },
          ] : {
          xPos   = (index % 2) * 6
          yPos   = floor(index / 2) * 4
          width  = 6
          height = 4
          widget = {
            title = tile.title
            xyChart = {
              dataSets = [{
                plotType = "LINE"
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter      = tile.filter
                    aggregation = { alignmentPeriod = "60s", perSeriesAligner = "ALIGN_MEAN" }
                  }
                }
              }]
            }
          }
        }
      ]
    }
  })

  depends_on = [google_monitoring_metric_descriptor.custom]
}

output "alerts" {
  value = merge(
    { for key, policy in google_monitoring_alert_policy.threshold : key => policy.documentation[0].content },
    { api_errors = google_monitoring_alert_policy.api_errors.documentation[0].content },
    { metrics_absent = google_monitoring_alert_policy.metrics_absent.documentation[0].content },
  )
}

output "log_location" {
  value = google_logging_project_bucket_config.services.location
}
