# Infraestructura GCP del laboratorio:
#   - GKE Standard zonal con Workload Identity
#   - Artifact Registry para las imágenes de service-a / service-b
#   - GSA del OTel Collector con permisos para Cloud Logging / Cloud Trace

terraform {
  required_version = ">= 1.6"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 6.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  apis = [
    "container.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "logging.googleapis.com",
    "cloudtrace.googleapis.com",
    "monitoring.googleapis.com",
  ]
}

resource "google_project_service" "apis" {
  for_each           = toset(local.apis)
  service            = each.value
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "otel_lab" {
  location      = var.region
  repository_id = "otel-lab"
  format        = "DOCKER"
  description   = "Imágenes del laboratorio OpenTelemetry"
  depends_on    = [google_project_service.apis]
}

# --- Service account de los nodos (mínimo privilegio) ---
resource "google_service_account" "nodes" {
  account_id   = "otel-lab-nodes"
  display_name = "GKE nodes - otel-lab"
}

resource "google_project_iam_member" "nodes" {
  for_each = toset([
    "roles/artifactregistry.reader",
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
    "roles/monitoring.viewer",
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.nodes.email}"
}

# --- Clúster GKE ---
resource "google_container_cluster" "lab" {
  name                     = var.cluster_name
  location                 = var.zone
  remove_default_node_pool = true
  initial_node_count       = 1
  deletion_protection      = false

  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  depends_on = [google_project_service.apis]
}

resource "google_container_node_pool" "default" {
  name       = "default-pool"
  cluster    = google_container_cluster.lab.name
  location   = var.zone
  node_count = var.node_count

  node_config {
    machine_type    = var.machine_type
    disk_size_gb    = 50
    service_account = google_service_account.nodes.email
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]

    workload_metadata_config {
      mode = "GKE_METADATA"
    }
  }
}

# --- Identidad del OTel Collector (Workload Identity) ---
resource "google_service_account" "otel_collector" {
  account_id   = "otel-collector"
  display_name = "OTel Collector - otel-lab"
}

resource "google_project_iam_member" "otel_collector" {
  for_each = toset([
    "roles/logging.logWriter",
    "roles/cloudtrace.agent",
    "roles/monitoring.metricWriter",
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.otel_collector.email}"
}

# La KSA otel-lab/otel-collector puede actuar como la GSA otel-collector.
resource "google_service_account_iam_member" "otel_collector_wi" {
  service_account_id = google_service_account.otel_collector.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[${var.k8s_namespace}/otel-collector]"
  depends_on         = [google_container_cluster.lab]
}
