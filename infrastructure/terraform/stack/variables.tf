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

variable "vapid_public_key" {
  description = "Chave pública VAPID do Web Push (base64url), entregue ao navegador pela API (#41). Vazia desliga o push."
  type        = string
  default     = ""
}

variable "vapid_subject" {
  description = "Contato do remetente do Web Push (VAPID `sub`), ex.: mailto:plantao@empresa.com."
  type        = string
  default     = "mailto:alertas@jayv.dev"
}

variable "atlassian_client_id" {
  description = "Client ID do app OAuth 2.0 (3LO) da plataforma no Atlassian (#43). Vazio desliga o Jira; o secret vai em atlassian-client-secret."
  type        = string
  default     = ""
}

variable "llm_routing" {
  description = "Roteamento do modelo do Diagnóstico (#47, ADR-0020): fixed (sempre o maior), by_complexity (o menor nos casos simples) ou fast (sempre o menor). Mude só com a recomendação de aid_evaluation compare."
  type        = string
  default     = "fixed"

  validation {
    condition     = contains(["fixed", "by_complexity", "fast"], var.llm_routing)
    error_message = "llm_routing: fixed, by_complexity ou fast."
  }
}
