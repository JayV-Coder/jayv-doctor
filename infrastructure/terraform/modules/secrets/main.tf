variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "secret_ids" {
  type = set(string)
}

variable "accessors" {
  description = "Chave estável => segredo e member que pode lê-lo."
  type = map(object({
    secret = string
    member = string
  }))
}

# Só o contêiner: o valor entra por `gcloud secrets versions add`, para nunca parar no state.
resource "google_secret_manager_secret" "this" {
  for_each  = var.secret_ids
  project   = var.project_id
  secret_id = each.value

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
}

resource "google_secret_manager_secret_iam_member" "accessor" {
  for_each  = var.accessors
  project   = var.project_id
  secret_id = google_secret_manager_secret.this[each.value.secret].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = each.value.member
}

output "locations" {
  value = flatten([
    for secret in google_secret_manager_secret.this : [
      for replica in secret.replication[0].user_managed[0].replicas : replica.location
    ]
  ])
}

output "accessors" {
  value = var.accessors
}
