# Monitoreo: Prometheus + Grafana

Se usa el chart comunitario **kube-prometheus-stack**, que despliega Prometheus,
Grafana, Alertmanager, kube-state-metrics y node-exporter en un solo paso dentro
del clúster k3d. No requiere crear ninguna cuenta externa: Grafana se administra
con un usuario/contraseña locales al clúster.

## 1. Instalar el stack

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm install monitoring prometheus-community/kube-prometheus-stack \
  -n monitoring --create-namespace \
  -f Monitoring/values-monitoring.yaml
```

> El nombre de release **debe ser `monitoring`**: el `ServiceMonitor` del chart de
> la app (`inventory-chart/templates/servicemonitor.yaml`) usa la etiqueta
> `release: monitoring` para que el Prometheus Operator lo descubra.

Verifica que todo esté arriba:

```bash
kubectl get pods -n monitoring
```

## 2. Habilitar el scraping de la app

El chart de la app no expone el `ServiceMonitor` por defecto (para que se pueda
instalar sin depender de este stack). Actívalo:

```bash
helm upgrade --install inventory ./inventory-chart --set monitoring.enabled=true
```

Esto crea un `ServiceMonitor` que le dice a Prometheus que scrapee
`GET /metrics` del servicio cada 15s (el endpoint lo expone `prometheus-net.AspNetCore`,
ver [Program.cs](../Microservicios_y_Docker/src/InventoryService.Api/Program.cs)).

Confírmalo en Prometheus: `kubectl port-forward -n monitoring svc/monitoring-kube-prometheus-prometheus 9090:9090`,
abre <http://localhost:9090/targets> y busca `inventory-service`.

## 3. Acceder a Grafana

```bash
kubectl port-forward -n monitoring svc/monitoring-grafana 3000:80
```

Abre <http://localhost:3000>.

- **Usuario:** `admin`
- **Contraseña:** la que pusiste en `Monitoring/values-monitoring.yaml`
  (`grafana.adminPassword`), o recupérala si usaste la generada automáticamente:

  ```bash
  kubectl get secret -n monitoring monitoring-grafana \
    -o jsonpath="{.data.admin-password}" | base64 -d
  ```

## 4. Importar el dashboard

**Dashboards → New → Import**, sube [`inventory-service-dashboard.json`](./inventory-service-dashboard.json)
y selecciona tu datasource de Prometheus (`Prometheus`, ya viene preconfigurado
por el chart). Incluye:

- Pods listos / reinicios de contenedores.
- CPU y memoria por pod (vía cAdvisor/kube-state-metrics).
- Tasa de requests, latencia p95 y errores 5xx del API `/api/products` (métricas
  propias de la app, vía `prometheus-net`).

## 5. Alerta básica en Grafana

Grafana → **Alerting → Alert rules → New alert rule**:

1. **Query:** `sum(kube_pod_status_ready{condition="true", pod=~"inventory-service.*"})`
2. **Condition:** `IS BELOW 1` durante `2m` (dispara si no hay ningún pod listo).
3. **Folder/labels:** crea una carpeta `inventory-service`.
4. **Contact point:** para el laboratorio basta con el contact point `grafana-default-email`
   preconfigurado, o crea uno nuevo (Slack/webhook) en **Alerting → Contact points**.

Con eso ya tienes una alerta funcional de "servicio caído" para incluir en el informe.
