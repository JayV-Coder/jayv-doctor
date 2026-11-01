output "api_ip" {
  description = "Aponte o DNS de api_domain para este IP."
  value       = module.edge.ip_address
}

output "egress_ip" {
  description = "IP de saída: use nas restrições de rede do Supabase."
  value       = module.network.egress_ip
}

output "github_variables" {
  description = "Variáveis do GitHub Environment usadas pelo deploy."
  value = {
    GCP_PROJECT_ID   = var.project_id
    GCP_WIF_PROVIDER = module.deploy.workload_identity_provider
    GCP_DEPLOY_SA    = module.deploy.service_account_email
  }
}
