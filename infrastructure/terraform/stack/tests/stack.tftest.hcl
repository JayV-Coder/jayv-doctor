# Sem credenciais: o provider é simulado e as regras são verificadas sobre o plano.
mock_provider "google" {
  mock_data "google_project" {
    defaults = { number = "1234567890" }
  }
}

variables {
  app_url                  = "https://app.exemplo.test"
  project_id               = "aid-test"
  environment              = "staging"
  supabase_jwt_issuer      = "https://exemplo.supabase.co/auth/v1"
  supabase_publishable_key = "sb_publishable_teste"
  github_repository        = "JayV-Coder/jayv-doctor"
  github_environment       = "staging"
  api_domain               = "api.exemplo.test"
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
    condition     = toset(keys(module.workers)) == toset(["ingestion", "correlation", "diagnosis", "connectors", "relay"])
    error_message = "Um serviço por worker."
  }
}

run "cada_servico_tem_conta_propria_sem_chave_exportada" {
  command = plan

  assert {
    condition     = length(toset(concat([google_service_account.api.account_id], [for account in google_service_account.worker : account.account_id]))) == 6
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
    condition     = contains(keys(module.secrets.accessors), "smtp-url/api") && !contains(keys(module.secrets.accessors), "smtp-url/diagnosis")
    error_message = "Só a API envia e-mail."
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

run "api_chama_o_storage_do_mesmo_projeto_com_a_chave_publicavel" {
  command = plan

  assert {
    condition     = module.api.env["SUPABASE_URL"] == "https://exemplo.supabase.co"
    error_message = "A URL do Supabase sai do emissor do JWT: o Storage é do mesmo projeto do Auth."
  }
  assert {
    condition     = module.api.env["SUPABASE_PUBLISHABLE_KEY"] == "sb_publishable_teste"
    error_message = "A API usa a chave publicável no Storage."
  }
}

run "so_o_worker_de_ingestao_le_a_chave_de_servico" {
  command = plan

  assert {
    condition     = contains(keys(module.secrets.accessors), "supabase-service-role-key/ingestion") && !contains(keys(module.secrets.accessors), "supabase-service-role-key/api") && !contains(keys(module.secrets.accessors), "supabase-service-role-key/correlation")
    error_message = "A chave de serviço do Supabase é só do worker de ingestão."
  }
}

run "so_o_relay_publica_e_o_scheduler_o_chama" {
  command = plan

  assert {
    condition     = alltrue([for t in module.topics : toset(keys(t.publishers)) == toset(["relay"])])
    error_message = "Toda publicação passa pela outbox: só o relay publica."
  }
  assert {
    condition     = google_cloud_scheduler_job.outbox_relay.schedule == "* * * * *"
    error_message = "O relay roda a cada minuto."
  }
  assert {
    condition     = !contains(keys(google_cloud_run_v2_service_iam_member.pubsub_invoker), "relay")
    error_message = "O Pub/Sub não chama o relay."
  }
}

run "chave_secreta_do_supabase_e_recusada" {
  command = plan

  variables {
    supabase_publishable_key = "sb_secret_vazada"
  }
  expect_failures = [var.supabase_publishable_key]
}

run "ambiente_invalido_e_recusado" {
  command = plan

  variables {
    environment = "qa"
  }
  expect_failures = [var.environment]
}
