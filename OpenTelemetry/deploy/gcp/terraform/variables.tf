variable "project_id" {
  description = "ID del proyecto GCP"
  type        = string
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "zone" {
  type    = string
  default = "us-central1-a"
}

variable "cluster_name" {
  type    = string
  default = "otel-lab"
}

variable "node_count" {
  description = "2 × e2-standard-4 = 8 vCPU: cabe en la cuota inicial de CPUs de cuentas nuevas o en prueba"
  type        = number
  default     = 2
}

variable "machine_type" {
  description = "e2-standard-4 deja margen para kube-prometheus-stack + el stack del lab + carga k6"
  type        = string
  default     = "e2-standard-4"
}

variable "k8s_namespace" {
  type    = string
  default = "otel-lab"
}
