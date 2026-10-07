#!/usr/bin/env bash
# Despliegue en AWS ECS Fargate. Requiere: aws CLI, terraform, docker (buildx).
#   AWS_PROFILE=mi-cuenta-lab ./deploy.sh
# Para destruir todo:  (cd terraform && terraform destroy -var aws_profile=$AWS_PROFILE)
#
# IMPORTANTE: usa una cuenta personal / académica, no una cuenta corporativa.
set -euo pipefail

cd "$(dirname "$0")"
PROFILE="${AWS_PROFILE:-default}"
REGION="${AWS_REGION:-us-east-1}"
TAG="${TAG:-v1}"
TF="terraform -chdir=terraform"
VARS=(-var "aws_profile=$PROFILE" -var "region=$REGION" -var "image_tag=$TAG")

echo ">> Cuenta destino:"
aws sts get-caller-identity --profile "$PROFILE" --query '[Account,Arn]' --output text
read -r -p "¿Desplegar en esta cuenta? (y/N) " ok
[[ "$ok" == "y" ]] || exit 1

echo ">> 1/3 Repositorios ECR"
$TF init -input=false
$TF apply -input=false -auto-approve "${VARS[@]}" -target=aws_ecr_repository.this

echo ">> 2/3 Build & push (linux/arm64 para Fargate Graviton)"
REGISTRY=$($TF output -json ecr_repositories | python3 -c "import sys,json; print(json.load(sys.stdin)['service-a'].split('/')[0])")
aws ecr get-login-password --region "$REGION" --profile "$PROFILE" | docker login --username AWS --password-stdin "$REGISTRY"
for svc in service-a service-b; do
  docker buildx build --platform linux/arm64 --build-arg SERVICE=$svc \
    -t "$REGISTRY/otel-lab/$svc:$TAG" --push ../../services
done

echo ">> 3/3 Infraestructura completa (VPC, ALB, ECS, X-Ray, CloudWatch, AMP)"
$TF apply -input=false -auto-approve "${VARS[@]}"

URL=$($TF output -raw service_a_url)
cat <<MSG

Listo. service-a: $URL/docs   (los targets del ALB tardan ~1-2 min en quedar healthy)
Prueba:  curl -s -X POST $URL/api/orders -H 'content-type: application/json' \\
           -d '{"customer_id":"c-1","product_id":1,"quantity":3}'
Carga:   docker run --rm -v "\$PWD/../../benchmark/k6:/scripts" -v "\$PWD/../../benchmark/results:/results" \\
           -e BASE_URL=$URL -e VUS=100 -e DURATION=5m -e RUN_LABEL=aws-otel grafana/k6:2.3.0 run /scripts/load-test.js
Trazas:  $($TF output -raw xray_console)
Logs:    CloudWatch > Log groups > /otel-lab/ecs  y  /otel-lab/otlp-logs
MSG
