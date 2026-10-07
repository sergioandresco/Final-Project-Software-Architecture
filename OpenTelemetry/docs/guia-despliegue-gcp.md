# Guía — Despliegue en GCP (GKE) paso a paso y evidencias

Proyecto: `fundamentos-devops` · Región: `us-central1` · Zona: `us-central1-a` · Clúster: `otel-lab`

Todo lo hace `deploy/gcp/deploy.sh`. Abajo está cada paso por separado, con el comando y para qué
sirve.

---

## Paso 0 — Requisitos en la máquina local

| Qué | Comando | Para qué |
|---|---|---|
| Terraform | `brew tap hashicorp/tap && brew install hashicorp/tap/terraform` | Crear la infraestructura como código |
| Plugin de autenticación de GKE | `gcloud components install gke-gcloud-auth-plugin` | Que `kubectl` se autentique contra GKE con tu cuenta de Google |
| Credenciales para Terraform (ADC) | `gcloud auth application-default login` | Terraform no usa la sesión de `gcloud`; usa las *Application Default Credentials* |
| Proyecto de cuota | `gcloud auth application-default set-quota-project fundamentos-devops` | Cobrar las llamadas a APIs a este proyecto |

## Paso 1 — Infraestructura con Terraform (`deploy/gcp/terraform/`)

```bash
cd OpenTelemetry/deploy/gcp
terraform -chdir=terraform init
terraform -chdir=terraform apply -var project_id=fundamentos-devops
```

Crea **19 recursos** en unos 10 minutos (la mayor parte del tiempo se va en el clúster):

| Recurso | Para qué |
|---|---|
| `google_project_service` × 6 | Habilita las APIs: GKE, Artifact Registry, Cloud Build, Logging, Trace y Monitoring |
| `google_artifact_registry_repository` | Registro privado de imágenes Docker (`us-central1-docker.pkg.dev/fundamentos-devops/otel-lab`) |
| `google_service_account.nodes` + 4 roles | Identidad de los nodos con mínimo privilegio (leer imágenes, escribir logs y métricas) |
| `google_container_cluster` + `node_pool` | GKE Standard zonal con **Workload Identity**, 2 nodos `e2-standard-4` (8 vCPU) |
| `google_service_account.otel_collector` + 3 roles | Identidad del Collector: `logging.logWriter`, `cloudtrace.agent`, `monitoring.metricWriter` |
| `google_service_account_iam_member` (Workload Identity) | Permite que el pod del Collector (KSA `otel-lab/otel-collector`) actúe como esa GSA **sin llaves JSON** |

**Concepto clave, Workload Identity:** en lugar de montar una llave de cuenta de servicio en el pod,
GKE intercambia la identidad de Kubernetes por la de Google. El chart anota la ServiceAccount de
Kubernetes con `iam.gke.io/gcp-service-account: otel-collector@fundamentos-devops.iam.gserviceaccount.com`.

## Paso 2 — Conectar `kubectl` al clúster

```bash
gcloud container clusters get-credentials otel-lab --zone us-central1-a --project fundamentos-devops
kubectl get nodes
```

> Esto cambia tu contexto actual de `kubectl` al de GKE. Para volver al clúster local:
> `kubectl config use-context k3d-arquitectura`.

## Paso 3 — Construir imágenes con Cloud Build (sin Docker local)

```bash
gcloud builds submit ../../services --config cloudbuild.yaml \
  --substitutions=_REGISTRY=us-central1-docker.pkg.dev/fundamentos-devops/otel-lab,_TAG=v1
```

Sube la carpeta `services/` a Cloud Build, que ejecuta los dos `docker build` (service-a y service-b)
en máquinas `linux/amd64`, las mismas que los nodos de GKE, y publica las imágenes en Artifact
Registry. Tardó **1 min 18 s**.

## Paso 4 — Prometheus + Grafana (kube-prometheus-stack)

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm upgrade --install monitoring prometheus-community/kube-prometheus-stack \
  -n monitoring --create-namespace -f values-kube-prometheus-stack.yaml
```

Instala el **Prometheus Operator**, Prometheus y Grafana. `values-kube-prometheus-stack.yaml` agrega a
Grafana los datasources **Jaeger** y **Loki** con la correlación por `trace_id`, igual que en local.

## Paso 5 — Dashboard de Grafana como ConfigMap

```bash
kubectl -n monitoring create configmap otel-lab-dashboard \
  --from-file=../../observability/grafana/dashboards/otel-lab-dashboard.json \
  --dry-run=client -o yaml | kubectl label --local -f - grafana_dashboard=1 -o yaml | kubectl apply -f -
```

El *sidecar* de Grafana vigila los ConfigMaps con la etiqueta `grafana_dashboard=1` y los carga
automáticamente. Es el mismo JSON del entorno local.

## Paso 6 — La aplicación y el pipeline (chart Helm `otel-lab`)

```bash
helm upgrade --install otel-lab ../helm/otel-lab -n otel-lab --create-namespace \
  --set imageRegistry=us-central1-docker.pkg.dev/fundamentos-devops/otel-lab --set imageTag=v1 \
  --set-file collector.config=../../collector/otel-collector-gcp.yaml \
  --set collector.gcpProjectId=fundamentos-devops \
  --set collector.gcpServiceAccount=otel-collector@fundamentos-devops.iam.gserviceaccount.com
```

Despliega en el namespace `otel-lab`:

| Componente | Réplicas | Detalle |
|---|---|---|
| service-a | 2 | Service tipo **LoadBalancer**: IP pública para la API |
| service-b | 2 | ClusterIP (solo interno) |
| postgres | 1 | Almacenamiento efímero (laboratorio) |
| otel-collector | 1 | Config `otel-collector-gcp.yaml` montada como ConfigMap (`--set-file`) |
| jaeger | 1 | Jaeger v2 all-in-one |
| loki | 1 | Logs OTLP para Grafana Explore |
| ServiceMonitor | — | Prometheus descubre y scrapea `:8889` (métricas de la app) y `:8888` (métricas internas del Collector) |

**Diferencia con el entorno local:** el Collector de GCP envía las trazas **también a Cloud Trace** y
los logs **también a Cloud Logging** (exporter `googlecloud`), y detecta automáticamente atributos de
GCP (`cloud.region`, `k8s.cluster.name`) con el processor `resource_detection`.

## Paso 7 — Verificación (resultados obtenidos)

| Verificación | Resultado |
|---|---|
| Pods | 8/8 `Running` |
| API pública | `POST http://<EXTERNAL-IP>:8000/api/orders` → `CONFIRMED` con `trace_id` |
| Jaeger en GKE | Traza de 20 spans con service-a y service-b |
| Cloud Trace | La misma traza (20 spans) |
| Cloud Logging | "Orden creada" y "Stock reservado" vinculados al mismo `trace_id` |
| Prometheus | Targets `otel-collector/metrics-app` y `metrics-self` en **UP** |
| Grafana | Datasources Prometheus, Jaeger y Loki en OK; dashboard cargado |
| Carga k6 en el clúster (50 VUs × 3 min) | 100.8 req/s, p99 176.9 ms, 0.59% de errores (falla inyectada del 1%) |

## Paso 8 — Generar carga para las capturas

```bash
cd OpenTelemetry/deploy/gcp
VUS=50 DURATION=3m RUN_LABEL=gke ./run-k6-in-cluster.sh
```

Corre el mismo script k6 como un **Job dentro del clúster**, contra `http://service-a:8000`, sin
pasar por internet.

---

## Capturas de pantalla para el informe

Guárdalas en `OpenTelemetry/evidencias/`. Antes de las capturas de Grafana y Jaeger, genera carga
(Paso 8) y espera 1–2 minutos.

### A. Entorno local (docker compose)

| # | Archivo | Dónde | Qué debe verse |
|---|---|---|---|
| 1 | `01-jaeger-traza.png` | http://localhost:16686 › Search › Service `service-a` › Operation `POST /api/orders` › abrir una traza | Cascada completa: service-a → service-b, spans custom y SQL |
| 2 | `02-jaeger-span.png` | En la misma traza, expandir `inventory.reserve_stock` | Atributos `inventory.*`, `order.ref` y `customer.id` (llegó por baggage) |
| 3 | `03-jaeger-dependencias.png` | Jaeger › System Architecture | Grafo service-a → service-b |
| 4 | `04-jaeger-error.png` | Search › Tags `error=true` | Traza con la falla inyectada (503 en service-b → 502 en service-a) |
| 5 | `05-grafana-dashboard.png` | http://localhost:3000 › Dashboards › OTel Lab · SLIs | Los 6 paneles con datos |
| 6 | `06-prometheus-targets.png` | http://localhost:9090/targets | Los 2 jobs del Collector en UP: **Prometheus es el backend de métricas** |
| 7 | `07-explore-log-traza.png` | Grafana › Explore › Loki: `{service_name="service-b"} \| trace_id != ""` › expandir una línea | Botón "Ver traza en Jaeger" |
| 8 | `08-explore-traza-logs.png` | Clic en ese botón | Vista dividida: log a la izquierda, traza a la derecha |
| 9 | `09-stdout-trace-id.png` | Terminal: `docker compose logs service-a service-b \| grep <trace_id>` | Mismo `trace_id` en los JSON de ambos servicios |
| 10 | `10-benchmark.png` | `benchmark/results/overhead-report.md` y `ablation/ablation-report.md` | Tablas de overhead |

### B. GCP (GKE)

Abre los túneles en dos terminales:

```bash
kubectl -n otel-lab port-forward svc/jaeger-query 16686:16686
```
```bash
kubectl -n monitoring port-forward svc/monitoring-grafana 3001:80
```

(Grafana de GKE: http://localhost:3001, usuario `admin`, contraseña `ChangeMe123!`)

| # | Archivo | Dónde | Qué debe verse |
|---|---|---|---|
| 11 | `11-gke-workloads.png` | [GKE › Workloads](https://console.cloud.google.com/kubernetes/workload/overview?project=fundamentos-devops) | Deployments del namespace `otel-lab` en OK |
| 12 | `12-gke-kubectl.png` | Terminal: `kubectl -n otel-lab get pods,svc` | 8 pods Running y la EXTERNAL-IP de service-a |
| 13 | `13-artifact-registry.png` | [Artifact Registry](https://console.cloud.google.com/artifacts/docker/fundamentos-devops/us-central1/otel-lab?project=fundamentos-devops) | Imágenes service-a y service-b |
| 14 | `14-cloud-build.png` | [Cloud Build › Historial](https://console.cloud.google.com/cloud-build/builds?project=fundamentos-devops) | Build exitoso |
| 15 | `15-gke-jaeger.png` | http://localhost:16686 (túnel) | Traza completa en el Jaeger de GKE |
| 16 | `16-cloud-trace.png` | [Cloud Trace › Explorador](https://console.cloud.google.com/traces/list?project=fundamentos-devops) | Traza `POST /api/orders` con sus spans |
| 17 | `17-cloud-logging.png` | [Logs Explorer](https://console.cloud.google.com/logs/query?project=fundamentos-devops) con la consulta `logName="projects/fundamentos-devops/logs/otel-lab"` | Logs con el campo **trace** y el enlace "Ver detalles del seguimiento" |
| 18 | `18-gke-grafana.png` | http://localhost:3001 › Dashboards › OTel Lab · SLIs | Dashboard con datos de GKE |
| 19 | `19-gke-k6.png` | Terminal de `run-k6-in-cluster.sh` | Resultado: req/s, p99 y errores |
| 20 | `20-terraform.png` | Terminal: `terraform -chdir=terraform state list` | Recursos creados por IaC |

---

## Pausar y reanudar (sin perder la configuración)

```bash
cd OpenTelemetry/deploy/gcp
PROJECT_ID=fundamentos-devops ./pause.sh    # 0 nodos + sin balanceador -> ~$0
PROJECT_ID=fundamentos-devops ./resume.sh   # vuelve a 2 nodos y re-crea el balanceador (~5-8 min)
```

En pausa se conservan el clúster (su plano de control lo cubre el crédito gratuito de GKE), las
imágenes de Artifact Registry, las cuentas de servicio, los releases de Helm y los logs y trazas en
Cloud Logging y Cloud Trace (30 días). Al reanudar, la IP pública de service-a cambia y Jaeger,
Loki y Prometheus empiezan vacíos.

## Paso final — Destruir todo (cuando ya no se necesite)

```bash
cd OpenTelemetry/deploy/gcp
helm uninstall otel-lab -n otel-lab
helm uninstall monitoring -n monitoring
terraform -chdir=terraform destroy -var project_id=fundamentos-devops
kubectl config use-context k3d-arquitectura
```

Primero van los `helm uninstall`, para que se elimine el balanceador de carga de service-a. Después,
`terraform destroy` borra el clúster, el registro y las cuentas de servicio.
