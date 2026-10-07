data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# Rol de ejecución: descargar imágenes de ECR y escribir logs del contenedor.
resource "aws_iam_role" "execution" {
  name               = "${local.name}-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Rol de tarea del Collector: solo los permisos de exportación que necesita.
resource "aws_iam_role" "collector" {
  name               = "${local.name}-collector"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role_policy_attachment" "collector_xray" {
  role       = aws_iam_role.collector.name
  policy_arn = "arn:aws:iam::aws:policy/AWSXrayWriteOnlyAccess"
}

data "aws_iam_policy_document" "collector" {
  statement {
    sid = "CloudWatchLogs"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogStreams",
      "logs:DescribeLogGroups",
    ]
    resources = ["${aws_cloudwatch_log_group.otlp.arn}:*", aws_cloudwatch_log_group.otlp.arn]
  }
  statement {
    sid       = "ManagedPrometheusRemoteWrite"
    actions   = ["aps:RemoteWrite"]
    resources = [aws_prometheus_workspace.this.arn]
  }
  statement {
    sid       = "EcsResourceDetection"
    actions   = ["ecs:DescribeTasks", "ecs:DescribeContainerInstances"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "collector" {
  name   = "otel-collector-exporters"
  role   = aws_iam_role.collector.id
  policy = data.aws_iam_policy_document.collector.json
}

# Rol de tarea de los servicios (sin permisos AWS: solo hablan OTLP con el Collector).
resource "aws_iam_role" "app" {
  name               = "${local.name}-app"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}
