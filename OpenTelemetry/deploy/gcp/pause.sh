#!/usr/bin/env bash
# Pausa el laboratorio en GKE sin borrar nada de la configuración:
#   1. service-a pasa a ClusterIP -> se elimina el balanceador de carga (lo único que cobra sin nodos).
#   2. El node pool baja a 0 nodos con Terraform -> no hay VMs ni discos.
# El plano de control zonal queda cubierto por el crédito gratuito de GKE.
#   PROJECT_ID=fundamentos-devops ./pause.sh
set -euo pipefail
cd "$(dirname "$0")"
PROJECT_ID="${PROJECT_ID:?Define PROJECT_ID}"

helm upgrade otel-lab ../helm/otel-lab -n otel-lab --reuse-values --set serviceA.serviceType=ClusterIP --wait
terraform -chdir=terraform apply -input=false -auto-approve -var "project_id=$PROJECT_ID" -var node_count=0
gcloud container clusters list --project "$PROJECT_ID" --format="table(name,status,currentNodeCount)"
echo "Laboratorio en pausa. Para reanudar: PROJECT_ID=$PROJECT_ID ./resume.sh"
