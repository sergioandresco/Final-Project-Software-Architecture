variable "region" {
  type    = string
  default = "us-east-1"
}

variable "aws_profile" {
  description = "Perfil del AWS CLI a usar (cuenta personal / académica del laboratorio)"
  type        = string
  default     = "default"
}

variable "allowed_cidr" {
  description = "CIDR autorizado a llegar al ALB (tu IP pública /32)"
  type        = string
  default     = "0.0.0.0/0"
}

variable "image_tag" {
  type    = string
  default = "v1"
}

variable "cpu_architecture" {
  description = "ARM64 permite usar las imágenes construidas en un Mac Apple Silicon (y Graviton es más barato)"
  type        = string
  default     = "ARM64"
}

variable "otel_sdk_disabled" {
  description = "true = modo baseline sin instrumentación (para el benchmark)"
  type        = bool
  default     = false
}

variable "chaos_failure_rate" {
  description = "Fracción de reservas en service-b que fallan a propósito (poblar paneles de error)"
  type        = number
  default     = 0.01
}
