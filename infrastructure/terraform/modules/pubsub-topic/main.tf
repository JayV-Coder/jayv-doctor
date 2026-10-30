variable "project_id" {
  type = string
}

variable "project_number" {
  type = string
}

variable "region" {
  type = string
}

variable "name" {
  type = string
}

variable "push_endpoint" {
  type = string
}

variable "push_audience" {
  type = string
}

variable "push_service_account_email" {
  type = string
}

variable "ack_deadline_seconds" {
  type    = number
  default = 60
}

variable "publishers" {
  description = "Nome do serviço => member do IAM."
  type        = map(string)
  default     = {}
}

locals {
  pubsub_agent = "serviceAccount:service-${var.project_number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

resource "google_pubsub_topic" "main" {
  project = var.project_id
  name    = var.name

  message_storage_policy {
    allowed_persistence_regions = [var.region]
  }
}

resource "google_pubsub_topic" "dead_letter" {
  project = var.project_id
  name    = "${var.name}.dlq"

  message_storage_policy {
    allowed_persistence_regions = [var.region]
  }
}

resource "google_pubsub_subscription" "push" {
  project              = var.project_id
  name                 = "${var.name}.push"
  topic                = google_pubsub_topic.main.id
  ack_deadline_seconds = var.ack_deadline_seconds

  push_config {
    push_endpoint = var.push_endpoint
    oidc_token {
      service_account_email = var.push_service_account_email
      audience              = var.push_audience
    }
  }

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.dead_letter.id
    max_delivery_attempts = 5
  }

  expiration_policy {
    ttl = ""
  }
}

# Sem assinatura, o que cai na DLQ é descartado. Fica 7 dias para inspeção e reprocessamento.
resource "google_pubsub_subscription" "dead_letter" {
  project                    = var.project_id
  name                       = "${var.name}.dlq.pull"
  topic                      = google_pubsub_topic.dead_letter.id
  message_retention_duration = "604800s"

  expiration_policy {
    ttl = ""
  }
}

# Sem estes dois, o Pub/Sub não move a mensagem para a DLQ, e ela volta a ser entregue para sempre.
resource "google_pubsub_topic_iam_member" "dead_letter_publisher" {
  project = var.project_id
  topic   = google_pubsub_topic.dead_letter.name
  role    = "roles/pubsub.publisher"
  member  = local.pubsub_agent
}

resource "google_pubsub_subscription_iam_member" "source_subscriber" {
  project      = var.project_id
  subscription = google_pubsub_subscription.push.name
  role         = "roles/pubsub.subscriber"
  member       = local.pubsub_agent
}

resource "google_pubsub_topic_iam_member" "publishers" {
  for_each = var.publishers
  project  = var.project_id
  topic    = google_pubsub_topic.main.name
  role     = "roles/pubsub.publisher"
  member   = each.value
}

output "max_delivery_attempts" {
  value = google_pubsub_subscription.push.dead_letter_policy[0].max_delivery_attempts
}

output "minimum_backoff" {
  value = google_pubsub_subscription.push.retry_policy[0].minimum_backoff
}

output "maximum_backoff" {
  value = google_pubsub_subscription.push.retry_policy[0].maximum_backoff
}

output "dead_letter_keeps_messages" {
  value = google_pubsub_subscription.dead_letter.message_retention_duration == "604800s"
}

output "storage_regions" {
  value = toset(concat(
    google_pubsub_topic.main.message_storage_policy[0].allowed_persistence_regions,
    google_pubsub_topic.dead_letter.message_storage_policy[0].allowed_persistence_regions,
  ))
}

output "uses_oidc" {
  value = length(google_pubsub_subscription.push.push_config[0].oidc_token) == 1
}
