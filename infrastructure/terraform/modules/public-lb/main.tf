variable "name_prefix" {
  type = string
}

variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "domain" {
  type = string
}

variable "cloud_run_service" {
  type = string
}

variable "rate_limit_per_minute" {
  type = number
}

resource "google_compute_global_address" "api" {
  project = var.project_id
  name    = "${var.name_prefix}-api"
}

resource "google_compute_region_network_endpoint_group" "api" {
  project               = var.project_id
  name                  = "${var.name_prefix}-api"
  region                = var.region
  network_endpoint_type = "SERVERLESS"

  cloud_run {
    service = var.cloud_run_service
  }
}

resource "google_compute_security_policy" "api" {
  project = var.project_id
  name    = "${var.name_prefix}-api"

  rule {
    action   = "rate_based_ban"
    priority = 1000
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    rate_limit_options {
      conform_action   = "allow"
      exceed_action    = "deny(429)"
      enforce_on_key   = "IP"
      ban_duration_sec = 300
      rate_limit_threshold {
        count        = var.rate_limit_per_minute
        interval_sec = 60
      }
    }
  }

  rule {
    action   = "allow"
    priority = 2147483647
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
  }
}

resource "google_compute_backend_service" "api" {
  project               = var.project_id
  name                  = "${var.name_prefix}-api"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  protocol              = "HTTPS"
  security_policy       = google_compute_security_policy.api.id

  backend {
    group = google_compute_region_network_endpoint_group.api.id
  }
}

resource "google_compute_url_map" "api" {
  project         = var.project_id
  name            = "${var.name_prefix}-api"
  default_service = google_compute_backend_service.api.id
}

resource "google_compute_managed_ssl_certificate" "api" {
  project = var.project_id
  name    = "${var.name_prefix}-api"

  managed {
    domains = [var.domain]
  }
}

resource "google_compute_target_https_proxy" "api" {
  project          = var.project_id
  name             = "${var.name_prefix}-api"
  url_map          = google_compute_url_map.api.id
  ssl_certificates = [google_compute_managed_ssl_certificate.api.id]
}

resource "google_compute_global_forwarding_rule" "https" {
  project               = var.project_id
  name                  = "${var.name_prefix}-api-https"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  ip_address            = google_compute_global_address.api.id
  port_range            = "443"
  target                = google_compute_target_https_proxy.api.id
}

output "ip_address" {
  value = google_compute_global_address.api.address
}

output "rate_limit_action" {
  value = one([for rule in google_compute_security_policy.api.rule : rule.action if rule.priority == 1000])
}

output "rate_limit_key" {
  value = one([for rule in google_compute_security_policy.api.rule : rule.rate_limit_options[0].enforce_on_key if rule.priority == 1000])
}
