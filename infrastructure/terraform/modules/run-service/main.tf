variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "name" {
  type = string
}

variable "service_account_email" {
  type = string
}

variable "ingress" {
  type = string
}

variable "public_invoker" {
  description = "Dispensa o IAM na invocação. Só para serviço que autentica por conta própria."
  type        = bool
}

variable "subnetwork" {
  type = string
}

variable "env" {
  type    = map(string)
  default = {}
}

variable "secret_env" {
  description = "Variável de ambiente => id do segredo."
  type        = map(string)
  default     = {}
}

variable "min_instances" {
  type    = number
  default = 0
}

variable "max_instances" {
  type    = number
  default = 10
}

variable "memory" {
  type    = string
  default = "512Mi"
}

variable "timeout" {
  type    = string
  default = "60s"
}

variable "deletion_protection" {
  type = bool
}

resource "google_cloud_run_v2_service" "this" {
  project              = var.project_id
  name                 = var.name
  location             = var.region
  ingress              = var.ingress
  invoker_iam_disabled = var.public_invoker
  deletion_protection  = var.deletion_protection

  template {
    service_account = var.service_account_email
    timeout         = var.timeout

    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    vpc_access {
      egress = "ALL_TRAFFIC"
      network_interfaces {
        subnetwork = var.subnetwork
      }
    }

    containers {
      # Só o primeiro apply usa esta imagem; depois quem publica é o deploy.yml.
      image = "us-docker.pkg.dev/cloudrun/container/hello"

      resources {
        limits = { cpu = "1", memory = var.memory }
      }

      dynamic "env" {
        for_each = var.env
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = var.secret_env
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }
    }
  }

  lifecycle {
    # A imagem é do deploy.yml: sem isto, todo plan depois de um deploy mostraria diff.
    ignore_changes = [
      client,
      client_version,
      template[0].containers[0].image,
      template[0].revision,
    ]
  }
}

output "name" {
  value = google_cloud_run_v2_service.this.name
}

output "uri" {
  value = google_cloud_run_v2_service.this.uri
}

output "ingress" {
  value = google_cloud_run_v2_service.this.ingress
}

output "public_invoker" {
  value = google_cloud_run_v2_service.this.invoker_iam_disabled
}
