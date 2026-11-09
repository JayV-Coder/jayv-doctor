variable "project_id" {
  type = string
}

variable "environment" {
  type = string

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Ambiente deve ser dev, staging ou prod."
  }
}

variable "region" {
  type    = string
  default = "southamerica-east1"
}

variable "api_domain" {
  description = "Domínio público da API; o certificado gerenciado só ativa com o DNS apontando para o IP."
  type        = string
}

variable "app_url" {
  description = "URL do app web, usada nos links de convite."
  type        = string
}

variable "supabase_jwt_issuer" {
  description = "Emissor dos JWTs do Supabase Auth. Não é segredo: as chaves vêm do JWKS público."
  type        = string
}

variable "supabase_publishable_key" {
  description = "Chave publicável do Supabase (a mesma do app web). Não é segredo: a API a usa no Storage junto com o JWT do Usuário."
  type        = string

  validation {
    condition     = startswith(var.supabase_publishable_key, "sb_publishable_")
    error_message = "Use a chave publicável (sb_publishable_…), nunca a secreta."
  }
}

variable "github_repository" {
  type = string
}

variable "github_environment" {
  description = "GitHub Environment que pode publicar neste projeto."
  type        = string
}

variable "api_min_instances" {
  type    = number
  default = 0
}

variable "rate_limit_per_minute" {
  description = "Requisições por minuto por IP antes do Cloud Armor responder 429."
  type        = number
  default     = 300
}

# Dimensionamento (#33, docs/operations/capacity.md). Com NullPool, cada requisição em curso pode
# abrir uma conexão no Supavisor; o projeto é compartilhado com o jayv-coder (ADR-0009), então o
# Doctor fica com uma fatia dos clientes do pooler.
variable "api_max_instances" {
  type    = number
  default = 4
}

variable "api_concurrency" {
  type    = number
  default = 40
}

variable "worker_max_instances" {
  type    = number
  default = 3
}

variable "worker_concurrency" {
  type    = number
  default = 8
}

variable "supavisor_client_budget" {
  description = "Clientes do Supavisor reservados ao Doctor (o resto é do jayv-coder)."
  type        = number
  default     = 300
}

# Observabilidade (#34).
variable "alert_emails" {
  description = "E-mails do plantão que recebem os alertas da plataforma."
  type        = list(string)
  default     = []
}

variable "oncall_webhook_url" {
  description = "Webhook do canal de plantão (vazio: só e-mail)."
  type        = string
  default     = ""
  sensitive   = true
}

variable "platform_operators" {
  description = "Quem abre o /admin/health do relay (ex.: group:operacao@empresa.com)."
  type        = list(string)
  default     = []
}
