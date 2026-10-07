#!/usr/bin/env bash
# Reanuda el laboratorio pausado con pause.sh: vuelve a 2 nodos y re-crea el balanceador de service-a.
# Los pods (app, Collector, Jaeger, Loki, Prometheus, Grafana) se reprograman solos al haber nodos.
# Nota: la IP pública de service-a cambia y los datos en memoria (Jaeger/Loki/Prometheus) empiezan vacíos.
#   PROJECT_ID=fundamentos-devops ./resume.sh
set -euo pipefail
cd "$(dirname "$0")"
PROJECT_ID="${PROJECT_ID:?Define PROJECT_ID}"

terraform -chdir=terraform apply -input=false -auto-approve -var "project_id=$PROJECT_ID" -var node_count=2
eval "$(terraform -chdir=terraform output -raw get_credentials)"
helm upgrade otel-lab ../helm/otel-lab -n otel-lab --reuse-values --set serviceA.serviceType=LoadBalancer --wait --timeout 10m
kubectl -n monitoring rollout status statefulset/prometheus-monitoring-kube-prometheus-prometheus --timeout=5m || true
kubectl -n otel-lab get pods,svc
echo "Espera 1-2 min a que service-a tenga EXTERNAL-IP: kubectl -n otel-lab get svc service-a -w"
