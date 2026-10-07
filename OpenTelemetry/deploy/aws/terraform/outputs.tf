output "service_a_url" {
  value = "http://${aws_lb.this.dns_name}"
}

output "ecr_repositories" {
  value = { for k, r in aws_ecr_repository.this : k => r.repository_url }
}

output "amp_workspace_endpoint" {
  description = "URL para el datasource Prometheus (SigV4) en Grafana"
  value       = aws_prometheus_workspace.this.prometheus_endpoint
}

output "xray_console" {
  value = "https://${var.region}.console.aws.amazon.com/cloudwatch/home?region=${var.region}#xray:traces/query"
}

output "cluster_name" {
  value = aws_ecs_cluster.this.name
}
