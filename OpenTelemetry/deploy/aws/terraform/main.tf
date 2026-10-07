# Infraestructura AWS del laboratorio (ECS Fargate):
#   VPC pública mínima · ECR · Cloud Map (DNS privado) · ALB para service-a
#   Tareas Fargate: postgres, service-b, service-a, otel-collector
#   Backends: AWS X-Ray (trazas) · CloudWatch Logs (logs) · Amazon Managed Prometheus (métricas)

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

provider "aws" {
  region  = var.region
  profile = var.aws_profile

  default_tags {
    tags = {
      Project = "otel-lab"
      Course  = "software-architecture"
    }
  }
}

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  name      = "otel-lab"
  namespace = "otel-lab.local"
  azs       = slice(data.aws_availability_zones.available.names, 0, 2)
}

# ---------------------------------------------------------------- Red
resource "aws_vpc" "this" {
  cidr_block           = "10.20.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags                 = { Name = local.name }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
}

# Subredes públicas: las tareas usan IP pública para descargar imágenes sin NAT Gateway (ahorro de costo).
resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.this.id
  cidr_block              = cidrsubnet(aws_vpc.this.cidr_block, 8, count.index)
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = true
  tags                    = { Name = "${local.name}-public-${count.index}" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_security_group" "alb" {
  name   = "${local.name}-alb"
  vpc_id = aws_vpc.this.id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = [var.allowed_cidr]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "tasks" {
  name   = "${local.name}-tasks"
  vpc_id = aws_vpc.this.id

  # Tráfico este-oeste dentro de la VPC (service-a -> service-b, OTLP -> collector, postgres).
  ingress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [aws_vpc.this.cidr_block]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ---------------------------------------------------------------- Service discovery
resource "aws_service_discovery_private_dns_namespace" "this" {
  name = local.namespace
  vpc  = aws_vpc.this.id
}

resource "aws_service_discovery_service" "this" {
  for_each = toset(["postgres", "service-b", "otel-collector"])
  name     = each.value

  dns_config {
    namespace_id   = aws_service_discovery_private_dns_namespace.this.id
    routing_policy = "MULTIVALUE"
    dns_records {
      type = "A"
      ttl  = 10
    }
  }
  # Salud gestionada por ECS (el health check de Cloud Map ya no admite parámetros).
  health_check_custom_config {}
}

# ---------------------------------------------------------------- ECR
resource "aws_ecr_repository" "this" {
  for_each             = toset(["service-a", "service-b"])
  name                 = "${local.name}/${each.value}"
  force_delete         = true
  image_tag_mutability = "MUTABLE"
}

# ---------------------------------------------------------------- ALB (entrada pública a service-a)
resource "aws_lb" "this" {
  name               = local.name
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id
}

resource "aws_lb_target_group" "service_a" {
  name        = "${local.name}-service-a"
  port        = 8000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = aws_vpc.this.id

  health_check {
    path                = "/health/ready"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 15
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.service_a.arn
  }
}
