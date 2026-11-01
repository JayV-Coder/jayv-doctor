terraform {
  required_version = ">= 1.9"

  # Bucket por ambiente em environments/<ambiente>.backend.hcl; o GCS faz o lock do state.
  backend "gcs" {}

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
