# Sem credenciais: o provider é simulado e as regras são verificadas sobre o plano.
mock_provider "google" {
  mock_data "google_project" {
    defaults = { number = "1234567890" }
  }
}

variables {
  project_id          = "aid-test"
  environment         = "staging"
  supabase_jwt_issuer = "https://exemplo.supabase.co/auth/v1"
  github_repository   = "JayV-Coder/jayv-doctor"
  github_environment  = "staging"
  api_domain          = "api.exemplo.test"
}

run "topicos_tem_push_autenticado_e_dlq_apos_5_tentativas" {
  command = plan

  assert {
    condition = toset(keys(module.topics)) == toset([
      "ingestion.raw", "ingestion.normalized", "correlation.requested", "diagnosis.requested", "connector.sync",
    ])
    error_message = "Os cinco tópicos do ticket precisam existir."
  }
  assert {
    condition     = alltrue([for t in module.topics : t.max_delivery_attempts == 5])
    error_message = "A DLQ recebe a mensagem após 5 tentativas."
  }
  assert {
    condition     = alltrue([for t in module.topics : t.minimum_backoff == "10s" && t.maximum_backoff == "600s"])
    error_message = "A política de retry deve ser exponencial."
  }
  assert {
    condition     = alltrue([for t in module.topics : t.dead_letter_keeps_messages])
    error_message = "A DLQ precisa de assinatura, senão a mensagem some."
  }
  assert {
    condition     = alltrue([for t in module.topics : t.uses_oidc])
    error_message = "O push precisa ser autenticado por OIDC."
  }
}

run "workers_sao_privados_e_a_api_so_entra_pelo_load_balancer" {
  command = plan

  assert {
    condition     = alltrue([for w in module.workers : w.ingress == "INGRESS_TRAFFIC_INTERNAL_ONLY" && !w.public_invoker])
    error_message = "Workers não aceitam chamada pública."
  }
  assert {
    condition     = module.api.ingress == "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
    error_message = "A API não pode ficar exposta fora do Load Balancer."
  }
  assert {
    condition     = toset(keys(module.workers)) == toset(["ingestion", "correlation", "diagnosis", "connectors"])
    error_message = "Um serviço por worker."
  }
}

run "cada_servico_tem_conta_propria_sem_chave_exportada" {
  command = plan

  assert {
    condition     = length(toset(concat([google_service_account.api.account_id], [for account in google_service_account.worker : account.account_id]))) == 5
    error_message = "API e workers usam service accounts separadas."
  }
}

run "segredos_ficam_no_brasil_e_cada_servico_le_so_o_seu" {
  command = plan

  assert {
    condition     = alltrue([for location in module.secrets.locations : location == "southamerica-east1"])
    error_message = "Segredos replicados só em southamerica-east1."
  }
  assert {
    condition     = !contains(keys(module.secrets.accessors), "anthropic-api-key/api")
    error_message = "A API não lê chave de LLM."
  }
  assert {
    condition     = contains(keys(module.secrets.accessors), "hmac-master-key/api") && !contains(keys(module.secrets.accessors), "hmac-master-key/correlation")
    error_message = "A chave HMAC mestre vai para quem calcula a Referência: API e ingestão."
  }
  assert {
    condition     = contains(keys(module.secrets.accessors), "anthropic-api-key/diagnosis")
    error_message = "O worker de diagnóstico lê a chave de LLM."
  }
}

run "mensagens_e_logs_ficam_no_brasil" {
  command = plan

  assert {
    condition     = alltrue([for t in module.topics : t.storage_regions == toset(["southamerica-east1"])])
    error_message = "Tópico e DLQ só persistem em southamerica-east1."
  }
  assert {
    condition     = module.observability.log_location == "southamerica-east1"
    error_message = "Logs dos serviços ficam em southamerica-east1."
  }
}

run "pubsub_espera_o_worker_terminar" {
  command = plan

  assert {
    condition = alltrue([
      for topic in values(local.topics) :
      topic.ack_deadline >= tonumber(trimsuffix(local.workers[topic.worker].timeout, "s"))
    ])
    error_message = "Ack menor que o timeout do worker reentrega mensagem em processamento."
  }
}

run "cloud_armor_limita_por_ip" {
  command = plan

  assert {
    condition     = module.edge.rate_limit_action == "throttle" && module.edge.rate_limit_key == "IP"
    error_message = "O Cloud Armor limita por IP."
  }
}

run "wif_aceita_so_este_repositorio_e_ambiente" {
  command = plan

  assert {
    condition     = strcontains(module.deploy.attribute_condition, "JayV-Coder/jayv-doctor") && strcontains(module.deploy.attribute_condition, "staging")
    error_message = "O WIF precisa restringir repositório e GitHub Environment."
  }
}

run "ambiente_invalido_e_recusado" {
  command = plan

  variables {
    environment = "qa"
  }
  expect_failures = [var.environment]
}
