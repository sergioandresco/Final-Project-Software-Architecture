#!/usr/bin/env bash
# Despliegue completo en GCP (GKE). Requiere: gcloud, terraform, kubectl, helm.
#   PROJECT_ID=fundamentos-devops ./deploy.sh
# Para destruir todo:  (cd terraform && terraform destroy -var project_id=$PROJECT_ID)
set -euo pipefail

cd "$(dirname "$0")"
PROJECT_ID="${PROJECT_ID:?Define PROJECT_ID}"
REGION="${REGION:-us-central1}"
ZONE="${ZONE:-us-central1-a}"
TAG="${TAG:-v1}"
NAMESPACE=otel-lab
ROOT=../..

echo ">> 1/5 Terraform: GKE + Artifact Registry + Workload Identity"
terraform -chdir=terraform init -input=false
terraform -chdir=terraform apply -input=false -auto-approve \
  -var "project_id=$PROJECT_ID" -var "region=$REGION" -var "zone=$ZONE"
REGISTRY=$(terraform -chdir=terraform output -raw registry_url)
COLLECTOR_GSA=$(terraform -chdir=terraform output -raw collector_gsa_email)
eval "$(terraform -chdir=terraform output -raw get_credentials)"

echo ">> 2/5 Cloud Build: imágenes service-a / service-b -> $REGISTRY"
gcloud builds submit "$ROOT/services" --project "$PROJECT_ID" --config cloudbuild.yaml \
  --substitutions="_REGISTRY=$REGISTRY,_TAG=$TAG"

echo ">> 3/5 kube-prometheus-stack (Prometheus + Grafana)"
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null
helm repo update >/dev/null
helm upgrade --install monitoring prometheus-community/kube-prometheus-stack \
  -n monitoring --create-namespace -f values-kube-prometheus-stack.yaml --wait --timeout 10m

echo ">> 4/5 Dashboard de Grafana (sidecar grafana_dashboard=1)"
kubectl -n monitoring create configmap otel-lab-dashboard \
  --from-file="$ROOT/observability/grafana/dashboards/otel-lab-dashboard.json" \
  --dry-run=client -o yaml | kubectl label --local -f - grafana_dashboard=1 -o yaml | kubectl apply -f -

echo ">> 5/5 Chart otel-lab (servicios + Collector + Jaeger + Loki)"
helm upgrade --install otel-lab "$ROOT/deploy/helm/otel-lab" -n "$NAMESPACE" --create-namespace \
  --set imageRegistry="$REGISTRY" --set imageTag="$TAG" \
  --set-file collector.config="$ROOT/collector/otel-collector-gcp.yaml" \
  --set collector.gcpProjectId="$PROJECT_ID" \
  --set collector.gcpServiceAccount="$COLLECTOR_GSA" \
  --wait --timeout 10m

kubectl -n "$NAMESPACE" get pods,svc
cat <<MSG

Listo. Accesos (port-forward):
  kubectl -n $NAMESPACE port-forward svc/jaeger-query 16686:16686
  kubectl -n monitoring port-forward svc/monitoring-grafana 3000:80      # admin / ChangeMe123!
  kubectl -n $NAMESPACE get svc service-a                                # EXTERNAL-IP para k6
Carga dentro del clúster:  ./run-k6-in-cluster.sh
MSG
