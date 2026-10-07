resource "aws_ecs_cluster" "this" {
  name = local.name
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

locals {
  db_url        = "postgresql+psycopg://otel:otel@postgres.${local.namespace}:5432/otel_lab"
  otlp_endpoint = "http://otel-collector.${local.namespace}:4317"

  # Variables OTel comunes a service-a y service-b.
  otel_env = [
    { name = "OTEL_EXPORTER_OTLP_ENDPOINT", value = local.otlp_endpoint },
    { name = "OTEL_EXPORTER_OTLP_INSECURE", value = "true" },
    { name = "OTEL_PROPAGATORS", value = "tracecontext,baggage" },
    { name = "OTEL_SEMCONV_STABILITY_OPT_IN", value = "http" },
    { name = "OTEL_SDK_DISABLED", value = tostring(var.otel_sdk_disabled) },
    { name = "OTEL_RESOURCE_ATTRIBUTES", value = "deployment.environment=aws-ecs,cloud.provider=aws" },
    { name = "DATABASE_URL", value = local.db_url },
  ]

  log_config = {
    for svc in ["postgres", "service-a", "service-b", "otel-collector"] : svc => {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.ecs.name
        awslogs-region        = var.region
        awslogs-stream-prefix = svc
      }
    }
  }

  # container va serializado con jsonencode para que todas las entradas del mapa tengan el mismo tipo.
  tasks = {
    postgres = {
      cpu = 512, memory = 1024, task_role = aws_iam_role.app.arn
      container = jsonencode({
        name         = "postgres"
        image        = "postgres:17.11"
        essential    = true
        command      = ["postgres", "-c", "max_connections=200"]
        portMappings = [{ containerPort = 5432, protocol = "tcp" }]
        environment = [
          { name = "POSTGRES_USER", value = "otel" },
          { name = "POSTGRES_PASSWORD", value = "otel" },
          { name = "POSTGRES_DB", value = "otel_lab" },
        ]
        healthCheck = {
          command  = ["CMD-SHELL", "pg_isready -U otel -d otel_lab"]
          interval = 10, timeout = 5, retries = 5, startPeriod = 20
        }
        logConfiguration = local.log_config["postgres"]
      })
    }

    "service-b" = {
      cpu = 1024, memory = 2048, task_role = aws_iam_role.app.arn
      container = jsonencode({
        name         = "service-b"
        image        = "${aws_ecr_repository.this["service-b"].repository_url}:${var.image_tag}"
        essential    = true
        portMappings = [{ containerPort = 8000, protocol = "tcp" }]
        environment = concat(local.otel_env, [
          { name = "OTEL_SERVICE_NAME", value = "service-b" },
          { name = "CHAOS_FAILURE_RATE", value = tostring(var.chaos_failure_rate) },
        ])
        logConfiguration = local.log_config["service-b"]
      })
    }

    "service-a" = {
      cpu = 1024, memory = 2048, task_role = aws_iam_role.app.arn
      container = jsonencode({
        name         = "service-a"
        image        = "${aws_ecr_repository.this["service-a"].repository_url}:${var.image_tag}"
        essential    = true
        portMappings = [{ containerPort = 8000, protocol = "tcp" }]
        environment = concat(local.otel_env, [
          { name = "OTEL_SERVICE_NAME", value = "service-a" },
          { name = "SERVICE_B_URL", value = "http://service-b.${local.namespace}:8000" },
        ])
        logConfiguration = local.log_config["service-a"]
      })
    }

    "otel-collector" = {
      cpu = 1024, memory = 2048, task_role = aws_iam_role.collector.arn
      container = jsonencode({
        name      = "otel-collector"
        image     = "otel/opentelemetry-collector-contrib:0.162.0"
        essential = true
        # La configuración completa viaja en una variable de entorno (provider env: del Collector).
        command = ["--config=env:OTEL_COLLECTOR_CONFIG"]
        portMappings = [
          { containerPort = 4317, protocol = "tcp" },
          { containerPort = 4318, protocol = "tcp" },
          { containerPort = 8888, protocol = "tcp" },
          { containerPort = 8889, protocol = "tcp" },
          { containerPort = 13133, protocol = "tcp" },
        ]
        environment = [
          { name = "OTEL_COLLECTOR_CONFIG", value = file("${path.module}/../../../collector/otel-collector-aws.yaml") },
          { name = "AWS_REGION", value = var.region },
          { name = "AMP_REMOTE_WRITE_URL", value = "${aws_prometheus_workspace.this.prometheus_endpoint}api/v1/remote_write" },
        ]
        logConfiguration = local.log_config["otel-collector"]
      })
    }
  }
}

resource "aws_ecs_task_definition" "this" {
  for_each                 = local.tasks
  family                   = "${local.name}-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = each.value.cpu
  memory                   = each.value.memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = each.value.task_role
  container_definitions    = "[${each.value.container}]"

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = var.cpu_architecture
  }
}

resource "aws_ecs_service" "this" {
  for_each        = local.tasks
  name            = each.key
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.this[each.key].arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = true
  }

  dynamic "service_registries" {
    for_each = contains(keys(aws_service_discovery_service.this), each.key) ? [1] : []
    content {
      registry_arn = aws_service_discovery_service.this[each.key].arn
    }
  }

  dynamic "load_balancer" {
    for_each = each.key == "service-a" ? [1] : []
    content {
      target_group_arn = aws_lb_target_group.service_a.arn
      container_name   = "service-a"
      container_port   = 8000
    }
  }

  depends_on = [aws_lb_listener.http]
}
