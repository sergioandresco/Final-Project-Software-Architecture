output "registry_url" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.otel_lab.repository_id}"
}

output "collector_gsa_email" {
  value = google_service_account.otel_collector.email
}

output "get_credentials" {
  value = "gcloud container clusters get-credentials ${google_container_cluster.lab.name} --zone ${var.zone} --project ${var.project_id}"
}
