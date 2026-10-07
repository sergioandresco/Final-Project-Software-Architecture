# Backends de observabilidad administrados en AWS.

# stdout de los contenedores (logs JSON con trace_id/span_id).
resource "aws_cloudwatch_log_group" "ecs" {
  name              = "/otel-lab/ecs"
  retention_in_days = 7
}

# Logs OTLP exportados por el Collector (awscloudwatchlogs exporter).
resource "aws_cloudwatch_log_group" "otlp" {
  name              = "/otel-lab/otlp-logs"
  retention_in_days = 7
}

# Amazon Managed Service for Prometheus: destino del remote write del Collector.
resource "aws_prometheus_workspace" "this" {
  alias = local.name
}
