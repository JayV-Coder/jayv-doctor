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

variable "supabase_jwt_issuer" {
  description = "Emissor dos JWTs do Supabase Auth. Não é segredo: as chaves vêm do JWKS público."
  type        = string
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
