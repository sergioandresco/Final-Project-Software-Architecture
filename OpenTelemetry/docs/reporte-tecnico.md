## 1. Introducción

Este laboratorio implementa un pipeline de observabilidad de extremo a extremo basado en
OpenTelemetry (OTel) para una aplicación de dos microservicios: service-a, que recibe órdenes de
compra, y service-b, que administra el inventario. Los dos dependen entre sí por HTTP y comparten una
base de datos PostgreSQL. El objetivo es capturar los tres pilares de la observabilidad desde el
código hasta los backends: métricas en Prometheus, logs estructurados y trazas distribuidas en
Jaeger. Además, se busca que las tres señales se puedan correlacionar a partir de un mismo
identificador, el `trace_id`, que viaja con cada request según el estándar W3C Trace Context (W3C,
2021).

El trabajo se organizó en las cuatro fases del enunciado: instrumentación con el SDK, despliegue del
OpenTelemetry Collector, backends y visualización, y análisis del costo de la instrumentación
(overhead). El pipeline se ejecutó en un entorno local con Docker y se desplegó en Google Cloud sobre
GKE. La infraestructura para AWS (ECS Fargate) quedó definida y validada como código, pero no se
desplegó, por las razones que se explican en la sección 7.

<p class="tnum">Tabla 1</p>
<p class="ttit">Datos generales del laboratorio</p>

| Dimensión | Dato |
|---|---|
| Aplicación | service-a (Orders API) → service-b (Inventory API), Python 3.12, FastAPI, SQLAlchemy, PostgreSQL 17 |
| Señales | Trazas (OTLP → Jaeger / Cloud Trace / X-Ray), métricas (OTLP → Prometheus), logs JSON con `trace_id` (OTLP → Loki / Cloud Logging / CloudWatch) |
| Entornos | Local (docker compose, Colima), GCP (GKE Standard, 2 nodos `e2-standard-4`), AWS (ECS Fargate, definido en Terraform) |
| Versiones | OTel Python SDK 1.45 · OTel Collector contrib 0.162 · Jaeger 2.20 · Prometheus 3.13 · Loki 3.7 · Grafana 13 · k6 2.3 |
| Repositorio | github.com/sergioandresco/Final-Project-Software-Architecture, carpeta `OpenTelemetry/` |

## 2. Arquitectura de la solución

La arquitectura separa con claridad tres responsabilidades. Los servicios **generan** la telemetría
mediante el SDK de OpenTelemetry. El Collector la **recibe, procesa y enruta**. Los backends la
**almacenan y la muestran**. Los servicios solo conocen el protocolo OTLP y la dirección del
Collector; qué backend recibe cada señal es una decisión de configuración del Collector, distinta
para cada entorno. Por eso el mismo código funciona sin cambios en local, en GCP y en AWS.

<p class="tnum">Figura 1</p>
<p class="ftit">Arquitectura del pipeline de observabilidad</p>

```mermaid
flowchart TB
    k6["k6 · 50–100 usuarios"] -->|HTTP| A["service-a · Orders API"]
    A -->|"HTTP + traceparent/baggage W3C"| B["service-b · Inventory API"]
    A -->|SQL| DB[(PostgreSQL)]
    B -->|"SQL (SELECT … FOR UPDATE)"| DB
    A -. "OTLP gRPC" .-> C["OTel Collector · memory_limiter → resource → batch"]
    B -. "OTLP gRPC" .-> C
    C -->|trazas| J["Jaeger · Cloud Trace · X-Ray"]
    C -->|"métricas :8889"| P["Prometheus · AMP"]
    C -->|logs| L["Loki · Cloud Logging · CloudWatch"]
    P --> G["Grafana"]
    J --> G
    L --> G
```

<p class="nota"><i>Nota.</i> Elaboración propia. Las líneas punteadas indican envío de telemetría por OTLP;
las continuas, tráfico de la aplicación.</p>

Una orden (`POST /api/orders`) produce una traza de unos 20 spans que cruza ambos servicios (tabla
2). Una parte de esos spans la crea la auto-instrumentación (HTTP servidor, HTTP cliente y SQL) y
otra la crean los spans propios que se agregaron alrededor de la lógica de negocio.

<p class="tnum">Tabla 2</p>
<p class="ttit">Recorrido de una orden y spans que genera</p>

| Paso | Servicio | Span | Origen |
|---|---|---|---|
| Recepción de la orden | service-a | `POST /api/orders` | Automático (FastAPI) |
| Validación | service-a | `orders.validate` | Propio |
| Reserva de inventario | service-a | `orders.reserve_inventory` → `POST` (cliente) | Propio + automático (httpx), que inyecta `traceparent` |
| Reserva en inventario | service-b | `POST /api/products/{id}/reserve` | Automático; extrae `traceparent` y continúa la misma traza |
| Lógica de reserva | service-b | `inventory.reserve_stock` | Propio |
| Acceso a datos | service-b | `SELECT … FOR UPDATE`, `UPDATE`, `INSERT` | Automático (SQLAlchemy) |
| Cálculo del total | service-a | `orders.calculate_total` | Propio |
| Persistencia de la orden | service-a | `INSERT orders` | Automático (SQLAlchemy) |

## 3. Fase 1: instrumentación con el SDK de OpenTelemetry

La configuración común de ambos servicios vive en el módulo `services/shared/telemetry.py`. Se eligió
**instrumentación programática** en lugar del agente automático (`opentelemetry-instrument`) por dos
razones. Primero, permite apagar toda la telemetría con `OTEL_SDK_DISABLED=true` sin cambiar la
imagen, que es el modo de comparación del benchmark. Segundo, permite activar o desactivar cada señal
por separado con las variables estándar `OTEL_{TRACES,METRICS,LOGS}_EXPORTER=none`, que se usaron en
el análisis por componente.

La **auto-instrumentación** cubre los tres puntos de entrada y salida de cada servicio: el servidor
HTTP (FastAPI), el cliente HTTP (httpx) y la base de datos (SQLAlchemy). Sobre ella se agregaron
**spans propios** solo en la lógica de negocio crítica, con atributos que dan contexto al
diagnóstico, como el número de orden, el total y el stock restante, y eventos como
`inventory.insufficient_stock`. Para que los paneles de errores y las trazas con estado de error
tuvieran datos reales, service-b incluye una **inyección de fallas** controlada: el 1% de las
reservas responde 503 a propósito.

La **propagación de contexto** usa W3C Trace Context y Baggage. El encabezado `traceparent` lleva el
identificador de la traza de service-a a service-b, y el baggage transporta el identificador del
cliente, que service-b agrega como atributo de su span. Los **logs** se escriben en JSON en la salida
estándar con el `trace_id` y el `span_id` del span activo, y en paralelo se envían por OTLP. Así, la
misma línea de log se puede encontrar por su identificador de traza en cualquier backend.

<p class="tnum">Tabla 3</p>
<p class="ttit">Señales emitidas por los servicios</p>

| Señal | Qué se emite | Cómo |
|---|---|---|
| Trazas | Spans HTTP, SQL y de negocio con atributos semánticos | `TracerProvider` + `BatchSpanProcessor` → OTLP/gRPC |
| Métricas | `http.server.request.duration`, `http.server.active_requests`, métricas de negocio (`orders.created`, `inventory.reservations`) y CPU/memoria del proceso | `MeterProvider` + `PeriodicExportingMetricReader` (10 s) → OTLP/gRPC |
| Logs | JSON en stdout con `trace_id`/`span_id`, y el mismo registro por OTLP | `JsonFormatter` + `LoggingHandler` → OTLP/gRPC |
| Contexto | `traceparent`, `tracestate` y `baggage` entre servicios | Propagadores W3C TraceContext + Baggage |

Durante las pruebas aparecieron dos ajustes. FastAPI, desde su versión 0.140, trae una telemetría
propia que se activa sola al detectar los providers globales; se desactivó explícitamente para que
la única fuente de spans fuera la instrumentación contrib. Además, las sondas de salud de Kubernetes
consultaban la base de datos cada 10 segundos y generaban trazas sin valor de negocio; esa consulta
se ejecuta ahora con la instrumentación suprimida.

## 4. Fase 2: despliegue del OpenTelemetry Collector

El Collector funciona como **gateway**: recibe la telemetría de todos los servicios, la procesa y la
envía a los backends. Tener este intermediario saca de la aplicación el agrupamiento, los reintentos
y la conversión de formatos, y permite cambiar de backend sin redesplegar los servicios. Hay una
configuración por entorno: `otel-collector-local.yaml`, `otel-collector-gcp.yaml` y
`otel-collector-aws.yaml`. Las tres se validaron con `otelcol-contrib validate`.

El orden de los procesadores sigue la recomendación del proyecto (tabla 4). `memory_limiter` va
primero, para rechazar datos antes de que el Collector se quede sin memoria. `resource` agrega
atributos comunes a las tres señales. `batch` va al final, para agrupar los envíos y reducir las
llamadas de red.

<p class="tnum">Tabla 4</p>
<p class="ttit">Pipeline del Collector</p>

| Componente | Configuración | Propósito |
|---|---|---|
| Receiver `otlp` | gRPC `:4317` y HTTP `:4318` | Recibir trazas, métricas y logs de los servicios |
| Processor `memory_limiter` | 400 MiB / pico 100 MiB (local); 80% / 20% (nube) | Aplicar *back-pressure* antes de un desbordamiento de memoria |
| Processor `resource_detection` | Detectores `gcp` o `ecs` (solo nube) | Agregar región, clúster y tarea automáticamente |
| Processor `resource` | `deployment.environment`, `collector.pipeline` | Enriquecer las tres señales con datos del entorno |
| Processor `batch` | Lotes de 1024–2048 elementos o 2 s | Reducir llamadas a los backends |
| Telemetría interna | Prometheus `:8888`, nivel `detailed` | Medir el propio Collector (CPU, datos rechazados, colas) |

<p class="tnum">Tabla 5</p>
<p class="ttit">Destino de cada señal según el entorno</p>

| Señal | Local | GCP (GKE) | AWS (ECS Fargate) |
|---|---|---|---|
| Trazas | Jaeger | Jaeger + Cloud Trace | AWS X-Ray |
| Métricas | Endpoint Prometheus `:8889` | Endpoint `:8889` + ServiceMonitor | Amazon Managed Prometheus (SigV4) + `:8889` |
| Logs | Loki | Cloud Logging + Loki | CloudWatch Logs |
| Credenciales | No aplica | Workload Identity, sin llaves | Rol IAM de la tarea |

En GCP el Collector se despliega en GKE con un chart de Helm y se autentica con **Workload
Identity**: la cuenta de servicio de Kubernetes actúa como una cuenta de servicio de Google con
permisos solo de escritura en Cloud Logging y Cloud Trace, así que no hay llaves JSON montadas en el
pod. En AWS se definió como un servicio Fargate cuya configuración viaja en una variable de entorno
(`--config=env:OTEL_COLLECTOR_CONFIG`), con un rol IAM limitado a X-Ray, CloudWatch Logs y escritura
en Amazon Managed Prometheus.

## 5. Fase 3: backends, visualización y correlación

### 5.1 Métricas y dashboard

Prometheus funciona como **base de datos de métricas**: cada cinco segundos lee el endpoint que expone
el Collector y guarda las series. Grafana no almacena métricas; las consulta en Prometheus y las
grafica. El dashboard tiene los seis paneles que pide el enunciado: cuatro indicadores de nivel de
servicio (SLI) que siguen las señales doradas (Beyer et al., 2016), el consumo de CPU y los errores
del propio Collector (tabla 6).

<p class="tnum">Tabla 6</p>
<p class="ttit">Paneles del dashboard de Grafana</p>

| Panel | Pregunta que responde | Consulta (resumen) |
|---|---|---|
| SLI 1 · Throughput | ¿Cuánto tráfico atiende cada servicio? | `rate(http_server_request_duration_seconds_count[1m])` |
| SLI 2 · Tasa de errores 5xx | ¿Qué porcentaje de requests falla? | errores 5xx / total |
| SLI 3 · Latencia p50/p95/p99 | ¿Qué tan rápido responde, incluso en el peor 1%? | `histogram_quantile` sobre el histograma de duración |
| SLI 4 · Disponibilidad | ¿Se cumple el objetivo de 99% de requests sin error? | 1 − errores / total (ventana de 5 min) |
| CPU | ¿Cuánto procesador usan los servicios y el Collector? | `rate(process_cpu_time_seconds_total[1m])` |
| Errores del Collector | ¿Se está perdiendo telemetría? | `otelcol_exporter_send_failed_*`, `otelcol_receiver_refused_*` |

### 5.2 Correlación entre señales con el trace_id

La correlación es lo que convierte tres herramientas separadas en un sistema de observabilidad.
Grafana se configuró para saltar entre señales usando el `trace_id` como pivote, siguiendo el modelo
de integración de trazas de Grafana Labs (s. f.). Desde una línea de log en Loki, el enlace "Ver
traza en Jaeger" abre la traza completa de ese request. Desde un span en Jaeger, el enlace inverso
muestra los logs con el mismo identificador. En la prueba, una orden produjo una traza de 20 spans, y
la búsqueda de su `trace_id` en Loki devolvió exactamente las dos líneas esperadas: "Orden creada"
de service-a y "Stock reservado" de service-b. En GCP la misma correlación es nativa: cada entrada de
Cloud Logging trae un campo `trace` que enlaza con su traza en Cloud Trace.

<p class="tnum">Tabla 7</p>
<p class="ttit">Mecanismos de correlación verificados</p>

| Dirección | Mecanismo | Resultado |
|---|---|---|
| Log → traza | Campo derivado de Loki sobre el metadato `trace_id` | Abre la traza en Jaeger dentro de Grafana |
| Traza → logs | `tracesToLogsV2` del datasource de Jaeger | Filtra Loki por el `trace_id` del span |
| Traza → métricas | `tracesToMetrics` | Muestra la latencia p99 del servicio del span |
| Respuesta → traza | service-a devuelve el encabezado `X-Trace-Id` | El cliente puede citar la traza al reportar un problema |
| Log en GCP → traza | Campo `trace` de Cloud Logging | Enlace directo a Cloud Trace |

### 5.3 Despliegue en Google Cloud

La infraestructura de GCP se creó con Terraform: 19 recursos, entre ellos el clúster GKE, el registro
de imágenes, las cuentas de servicio y la federación de identidad. Las imágenes se construyeron con
Cloud Build, y la aplicación, el Collector y los backends se instalaron con Helm. La verificación de
punta a punta se resume en la tabla 8.

<p class="tnum">Tabla 8</p>
<p class="ttit">Verificación del despliegue en GKE</p>

| Verificación | Resultado |
|---|---|
| Infraestructura | Clúster `otel-lab` con 2 nodos (8 vCPU, 32 GB) y 19 recursos gestionados por Terraform |
| Imágenes | Construidas con Cloud Build (1 min 18 s) y publicadas en Artifact Registry |
| Pods | 8/8 de la aplicación y 6/6 de monitoreo en estado Running |
| API pública | `POST /api/orders` por el balanceador de carga responde 201 con su `trace_id` |
| Trazas | La misma traza (20 spans, 2 servicios) en Jaeger y en Cloud Trace |
| Logs | Cloud Logging con el campo `trace` vinculado a Cloud Trace |
| Métricas | ServiceMonitor del Collector en estado UP; dashboard con datos de GKE |
| Carga (30 usuarios × 15 min) | 61.4 req/s, p95 73.8 ms, p99 120.3 ms y 0.63% de errores (la falla inyectada del 1%) |

## 6. Fase 4: análisis de overhead

### 6.1 Metodología

El benchmark se ejecutó en un portátil Apple M1 (8 núcleos, 8 GB) con Colima (6 vCPU, 8 GB). Cada
servicio estuvo limitado a 1 CPU y 512 MiB para que las corridas fueran comparables. Se hicieron dos
experimentos.

El primero, **experimento A**, cumple el requisito del enunciado: k6 con 100 usuarios concurrentes
durante 5 minutos, pausas de 200 a 800 ms entre acciones y una mezcla de 70% de órdenes, 20% de
consultas al catálogo y 10% de consultas de órdenes. Cada caso arrancó con el stack recién creado y
un calentamiento de 30 segundos. Se comparó la aplicación sin instrumentación, con instrumentación y
muestreo del 100%, y con instrumentación y muestreo del 10%. El segundo, **experimento B**, es una
ablación: cada señal se activó por separado con una tasa fija de unas 90 solicitudes por segundo,
por debajo de la saturación, para medir el **costo de CPU por solicitud** de cada componente.

### 6.2 Resultados

<p class="tnum">Tabla 9</p>
<p class="ttit">Experimento A: 100 usuarios concurrentes durante 5 minutos</p>

| Métrica | Sin OTel | OTel 100% | Variación | OTel 10% | Variación |
|---|---|---|---|---|---|
| Latencia p50 (ms) | 7.30 | 123.67 | +1593% | 157.62 | +2058% |
| Latencia p95 (ms) | 146.35 | 751.14 | +413% | 1216.76 | +731% |
| **Latencia p99 (ms)** | 445.90 | 1263.60 | **+818 ms (+183%)** | 3587.06 | +704% |
| Throughput (req/s) | 210.32 | 151.42 | −28.0% | 125.53 | −40.3% |
| CPU service-a (% de 1 núcleo) | 53.4 | 96.9 | +81% | 98.3 | +84% |
| CPU service-b (% de 1 núcleo) | 35.8 | 64.9 | +81% | 62.8 | +75% |
| Memoria service-a (MiB) | 73.2 | 95.4 | +30% | 93.2 | +27% |
| Memoria service-b (MiB) | 64.5 | 83.5 | +29% | 80.9 | +25% |
| OTel Collector (CPU / memoria) | No aplica | 6.6% / 85 MiB | | 5.2% / 81 MiB | |

<p class="tnum">Tabla 10</p>
<p class="ttit">Experimento B: costo por componente a tasa fija (~90 req/s)</p>

| Variante | p50 (ms) | p99 (ms) | CPU por request en estado estable (ms) | Variación | Tiempo saturado |
|---|---|---|---|---|---|
| Sin OTel | 4.6 | 60.2 | 3.15 | No aplica | 0% |
| Instrumentación sin providers (no-op) | 6.2 | 2120.6 | 4.42 | +1.27 ms (+40%) | 16% |
| Solo métricas | 5.5 | 380.3 | 4.18 | +1.03 ms (+33%) | 2% |
| Solo logs OTLP | 5.4 | 90.4 | 4.03 | +0.88 ms (+28%) | 0% |
| Solo trazas (100%) | 6.3 | 315.2 | 5.70 | +2.55 ms (+81%) | 2% |
| **Completo (100%)** | 22.1 | 1718.7 | **8.21** | **+5.06 ms (+161%)** | 29–67% |
| **Completo con muestreo 10%** | **7.1** | 937.0 | **5.89** | **+2.74 ms (+87%)** | **2%** |

<p class="nota"><i>Nota.</i> CPU por request en estado estable = suma de las medianas de CPU de ambos
servicios, sin contar los instantes saturados, dividida entre las solicitudes por segundo. Tiempo
saturado = porcentaje de muestras con service-a al 90% o más de su núcleo. La variación entre corridas
repetidas fue de unos ±0.3 ms.</p>

### 6.3 Análisis

Con 100 usuarios y pausas cortas, la aplicación sin instrumentar ya usa el 53% del núcleo de
service-a. La instrumentación completa la lleva a la saturación (97%). Desde ese punto la latencia
deja de reflejar el trabajo de cada solicitud y pasa a reflejar la **cola** de solicitudes en
espera. Por eso el experimento A mide, más que nada, la **pérdida de capacidad**: con la misma
infraestructura, el servicio instrumentado sostiene un 28% menos de tráfico. El caso con muestreo
del 10% salió peor que el de 100%, en contra de lo esperado. El experimento B mostró que esa
diferencia no se debe al muestreo, sino a episodios de saturación que aparecen de forma irregular
entre corridas.

El experimento B separa el costo intrínseco de cada señal. La configuración completa agrega unos
**5 ms de CPU por solicitud** (+161%) sumando los dos servicios. Las trazas son la señal más cara
(+2.6 ms), porque cada orden genera unos 20 spans. Las siguen las métricas (+1.0 ms) y los logs
(+0.9 ms). Una parte del costo corresponde a los envoltorios de instrumentación, que siguen activos
aun sin SDK. La memoria crece entre 18 y 22 MiB por servicio, alrededor de 30%. El Collector,
separado de la aplicación, consume entre 5% y 7% de un núcleo y unos 85 MiB.

El hallazgo más importante es la **inestabilidad metaestable**. Con todo activado, service-a corre
estable a cerca de 42% de CPU, pero un pico transitorio genera cola. En Python, los endpoints
síncronos comparten un grupo de 40 hilos que compiten por el GIL, así que con más cola cada solicitud
cuesta más CPU, y el sistema no vuelve a su estado estable aunque la carga promedio no lo justifique.
Bronson et al. (2021) describen este patrón como una falla metaestable. El servicio pasó entre 29% y
67% del tiempo saturado. Con muestreo head-based del 10%, el costo bajó a +2.7 ms por solicitud, la
mediana de latencia volvió a 7 ms y el tiempo saturado cayó a 2%. Los logs y las métricas siguen
emitiéndose para todas las solicitudes con su `trace_id`, así que la correlación se conserva para
las trazas muestreadas. Es el mismo principio de muestreo que propuso Dapper para sostener el
trazado distribuido a gran escala (Sigelman et al., 2010).

### 6.4 Recomendaciones

De los resultados se desprenden cuatro recomendaciones:

1. **Muestreo.** Usar muestreo head-based de 10% o menos en producción y, si se necesitan todas las
   trazas con error o lentas, agregar *tail sampling* en el Collector.
2. **Endpoints asíncronos o más réplicas.** Pasar los endpoints de entrada y salida a modo asíncrono
   (`httpx.AsyncClient`, SQLAlchemy asyncio) o escalar horizontalmente, para evitar la contención del
   grupo de hilos.
3. **Margen de capacidad.** Dejar un margen de capacidad del doble del CPU medido sin instrumentación
   al dimensionar servicios Python instrumentados.
4. **Granularidad de los spans SQL.** Revisar los spans SQL, que son la mayoría de cada traza, y
   filtrarlos o muestrearlos aparte si no aportan al diagnóstico.

## 7. Problemas encontrados y lecciones aprendidas

La implementación expuso varios problemas reales, propios de un ecosistema que cambia rápido (tabla
11). La mayoría no eran errores de código, sino diferencias entre versiones, o situaciones que solo
aparecen bajo carga sostenida. Esto refuerza la idea de que el pipeline de observabilidad también
debe observarse.

<p class="tnum">Tabla 11</p>
<p class="ttit">Problemas encontrados, diagnóstico y solución</p>

| Problema | Diagnóstico | Solución |
|---|---|---|
| El datasource de Jaeger en Grafana responde 404 | Jaeger 2.21 eliminó la API HTTP v1 que usa Grafana | Fijar Jaeger 2.20.0 |
| El Jaeger de GKE perdía todas las trazas | Guardaba hasta 100.000 trazas en memoria y fue terminado por falta de memoria (`OOMKilled`) | Limitar a 20.000 trazas (`max_traces`) |
| Cloud Trace lleno de trazas sin negocio | Las sondas de salud de Kubernetes consultaban la base de datos cada 10 s | Suprimir la instrumentación en `/health/ready` (40 sondas → 0 spans) |
| Panel de errores del Collector con error de consulta | `rate()` sobre una expresión regular del nombre de métrica deja series duplicadas | Consultas explícitas por métrica |
| Opción del Collector marcada como obsoleta | Su reemplazo (`resource_constant_labels`) no agregaba etiquetas en la versión 0.162 | Mantener la opción anterior y documentarlo |
| No aparecen exemplars en Prometheus | El SDK los genera, pero el exporter `prometheus` no los publica | Correlación métrica → traza desde Jaeger |
| Telemetría duplicada potencial en FastAPI | FastAPI 0.140+ trae telemetría propia que se autoconfigura | Desactivarla explícitamente |
| Incompatibilidad de versiones | La instrumentación de SQLAlchemy no soporta la versión 2.1 | Fijar SQLAlchemy 2.0.54 |
| Componentes renombrados en el Collector | `otlp` → `otlp_grpc`, `otlphttp` → `otlp_http` | Usar los nombres nuevos y validar la configuración |

En cuanto a limitaciones, el despliegue en **AWS no se ejecutó**: la única cuenta disponible es
corporativa y no se usó para fines académicos. El módulo de Terraform para ECS Fargate (red, balanceador,
descubrimiento de servicios, cuatro servicios, CloudWatch Logs, Amazon Managed Prometheus e IAM) pasa
`terraform validate`, y la configuración del Collector para AWS pasa `otelcol-contrib validate`, así
que queda listo para ejecutarse en una cuenta personal o académica. Además, el benchmark se hizo en un
portátil donde la carga y los servicios comparten la máquina, lo que introduce ruido entre corridas.
Por eso el análisis por componente usa tasa fija y medianas de estado estable.

## 8. Conclusiones

El pipeline cumple los objetivos del laboratorio. Los dos servicios emiten trazas, métricas y logs
con OpenTelemetry. El Collector desacopla la aplicación de los backends con una configuración por
entorno, el contexto W3C se propaga entre servicios, y el `trace_id` funciona como pivote entre las
tres señales, tanto en Grafana como en las herramientas nativas de GCP.

El análisis de overhead deja una lección que va más allá de la herramienta. La observabilidad
completa tiene un costo medible: unos 5 ms de CPU por solicitud y 30% más de memoria en servicios
Python. Con muestreo del 100%, además, reduce el margen de capacidad hasta volver frágil al servicio
bajo carga. El muestreo y el dimensionamiento son, por lo tanto, decisiones de diseño tan importantes
como la instrumentación misma. Con muestreo del 10% se conserva la correlación entre señales y el
costo se reduce casi a la mitad.

<div class="pagebreak"></div>

## Referencias

<div class="refs" markdown="1">

Beyer, B., Jones, C., Petoff, J., & Murphy, N. R. (Eds.). (2016). *Site reliability engineering: How Google runs production systems*. O'Reilly Media. https://sre.google/sre-book/table-of-contents/

Bronson, N., Aghayev, A., Charapko, A., & Zhu, T. (2021). Metastable failures in distributed systems. En *Proceedings of the Workshop on Hot Topics in Operating Systems (HotOS '21)* (pp. 221–227). ACM. https://doi.org/10.1145/3458336.3465286

Grafana Labs. (s. f.). *Trace integration in Explore*. Grafana documentation. https://grafana.com/docs/grafana/latest/explore/trace-integration/

Grafana Labs. (s. f.). *Grafana k6 documentation*. https://k6.io/docs/

Jaeger Authors. (s. f.). *Architecture*. Jaeger documentation. https://www.jaegertracing.io/docs/architecture/

OpenTelemetry Authors. (s. f.). *OpenTelemetry Python*. https://opentelemetry-python.readthedocs.io/

OpenTelemetry Authors. (s. f.). *Collector*. OpenTelemetry documentation. https://opentelemetry.io/docs/collector/

Prometheus Authors. (s. f.). *Overview*. Prometheus documentation. https://prometheus.io/docs/introduction/overview/

Sigelman, B. H., Barroso, L. A., Burrows, M., Stephenson, P., Plakal, M., Beaver, D., Jaspan, S., & Shanbhag, C. (2010). *Dapper, a large-scale distributed systems tracing infrastructure* (Google Technical Report dapper-2010-1). Google.

W3C. (2021). *Trace Context* (W3C Recommendation). https://www.w3.org/TR/trace-context/

</div>

<div class="pagebreak"></div>

## Anexo A. Evidencias

### Entorno local

<figure><p class="tnum">Figura 2</p><p class="ftit">Traza completa de una orden en Jaeger</p><img src="../evidencias/01-jaeger-traza.png"><p class="nota"><i>Nota.</i> 20 spans en 2 servicios y 6 niveles de profundidad: spans HTTP automáticos, spans propios (<code>orders.*</code>, <code>inventory.reserve_stock</code>) y consultas SQL.</p></figure>

<figure><p class="tnum">Figura 3</p><p class="ftit">Detalle de los spans de base de datos</p><img src="../evidencias/02-jaeger-span.png"><p class="nota"><i>Nota.</i> Atributos semánticos de la auto-instrumentación (<code>db.system</code>, <code>db.statement</code>) y del Resource agregado por el Collector.</p></figure>

<figure><p class="tnum">Figura 4</p><p class="ftit">Grafo de dependencias entre servicios</p><img src="../evidencias/03-jaeger-dependencias.png"><p class="nota"><i>Nota.</i> Jaeger construye la relación service-a → service-b a partir de la propagación del contexto W3C.</p></figure>

<figure><p class="tnum">Figura 5</p><p class="ftit">Búsqueda de trazas con error</p><img src="../evidencias/04a-jaeger-errores-busqueda.png"><p class="nota"><i>Nota.</i> Filtro <code>error=true</code> sobre las trazas afectadas por la falla inyectada del 1%.</p></figure>

<figure><p class="tnum">Figura 6</p><p class="ftit">Traza con error propagado entre servicios</p><img src="../evidencias/04b-jaeger-traza-error.png"><p class="nota"><i>Nota.</i> service-b responde 503 en la reserva y service-a lo traduce a 502.</p></figure>

<figure><p class="tnum">Figura 7</p><p class="ftit">Dashboard de indicadores de nivel de servicio bajo carga</p><img src="../evidencias/05-grafana-dashboard.png"></figure>

<figure><p class="tnum">Figura 8</p><p class="ftit">Prometheus como backend de métricas</p><img src="../evidencias/06-prometheus-targets.png"><p class="nota"><i>Nota.</i> Endpoints del Collector en estado UP: <code>:8889</code> (métricas de la aplicación) y <code>:8888</code> (métricas internas).</p></figure>

<figure><p class="tnum">Figura 9</p><p class="ftit">Consulta PromQL directa en Prometheus</p><img src="../evidencias/07-prometheus-query.png"></figure>

<figure><p class="tnum">Figura 10</p><p class="ftit">Logs de service-b en Loki con su trace_id</p><img src="../evidencias/08a-explore-loki.png"></figure>

<figure><p class="tnum">Figura 11</p><p class="ftit">Correlación de log a traza en Grafana Explore</p><img src="../evidencias/09a-explore-log-traza.png"><p class="nota"><i>Nota.</i> Desde una línea de log, el enlace "Ver traza en Jaeger" abre la traza del mismo <code>trace_id</code> en vista dividida.</p></figure>

<figure><p class="tnum">Figura 12</p><p class="ftit">Detalle de la traza abierta desde el log</p><img src="../evidencias/09b-explore-traza-detalle.png"></figure>

<figure><p class="tnum">Figura 13</p><p class="ftit">El mismo trace_id en los logs de ambos servicios</p><img src="../evidencias/10-stdout-trace-id.png"></figure>

<figure><p class="tnum">Figura 14</p><p class="ftit">Resultados del experimento A</p><img src="../evidencias/11a-benchmark-overhead.png"></figure>

<figure><p class="tnum">Figura 15</p><p class="ftit">Resultados del experimento B</p><img src="../evidencias/11c-benchmark-ablacion.png"></figure>

### Google Cloud (GKE)

<figure><p class="tnum">Figura 16</p><p class="ftit">Clúster GKE creado con Terraform</p><img src="../evidencias/12-gke-cluster.png"></figure>

<figure><p class="tnum">Figura 17</p><p class="ftit">Cargas de trabajo en los namespaces otel-lab y monitoring</p><img src="../evidencias/13-gke-workloads.png"></figure>

<figure><p class="tnum">Figura 18</p><p class="ftit">Servicios de Kubernetes y balanceador externo de service-a</p><img src="../evidencias/14-gke-servicios.png"></figure>

<figure><p class="tnum">Figura 19</p><p class="ftit">Imágenes publicadas en Artifact Registry</p><img src="../evidencias/15-artifact-registry.png"></figure>

<figure><p class="tnum">Figura 20</p><p class="ftit">Construcción de imágenes en Cloud Build</p><img src="../evidencias/16-cloud-build.png"></figure>

<figure><p class="tnum">Figura 21</p><p class="ftit">Traza en Cloud Trace</p><img src="../evidencias/17-cloud-trace.png"><p class="nota"><i>Nota.</i> Exportada por el Collector con el exporter <code>googlecloud</code>: 20 spans de service-a y service-b.</p></figure>

<figure><p class="tnum">Figura 22</p><p class="ftit">Log en Cloud Logging vinculado a su traza</p><img src="../evidencias/18-cloud-logging.png"><p class="nota"><i>Nota.</i> Los campos <code>trace</code> y <code>spanId</code> permiten la correlación nativa de log a traza en GCP.</p></figure>

<figure><p class="tnum">Figura 23</p><p class="ftit">Cuentas de servicio del laboratorio</p><img src="../evidencias/19-service-accounts.png"><p class="nota"><i>Nota.</i> <code>otel-collector</code> usa Workload Identity y no tiene llaves.</p></figure>

<figure><p class="tnum">Figura 24</p><p class="ftit">Traza en el Jaeger desplegado en GKE</p><img src="../evidencias/20-gke-jaeger.png"></figure>

<figure><p class="tnum">Figura 25</p><p class="ftit">Dashboard en el Grafana de GKE</p><img src="../evidencias/21-gke-grafana.png"></figure>

<figure><p class="tnum">Figura 26</p><p class="ftit">ServiceMonitor del Collector en el Prometheus de GKE</p><img src="../evidencias/22-gke-prometheus-targets.png"></figure>

<figure><p class="tnum">Figura 27</p><p class="ftit">Pods y servicios del namespace otel-lab</p><img src="../evidencias/23-kubectl.png"></figure>

<figure><p class="tnum">Figura 28</p><p class="ftit">Recursos de GCP gestionados con Terraform</p><img src="../evidencias/25-terraform.png"></figure>

<figure><p class="tnum">Figura 29</p><p class="ftit">Resumen de k6 ejecutado como Job dentro de GKE</p><pre>scenarios: (100.00%) 1 scenario, 30 max VUs, 15m10s max duration (incl. graceful stop):
         * steady_load: 30 looping VUs for 15m0s (gracefulStop: 10s)
[gke-evidencias] p99=120.3ms p95=73.8ms rps=61.4 errores=0.63%</pre></figure>
