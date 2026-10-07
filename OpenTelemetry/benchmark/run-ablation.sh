#!/usr/bin/env bash
# Análisis de overhead por componente (ablación). Misma tasa de llegada fija para
# cada variante, por debajo de la saturación, para medir el costo de CPU por request
# de cada señal de OpenTelemetry por separado.
#
# Uso (desde OpenTelemetry/):
#   ./benchmark/run-ablation.sh                  # RATE=80 iteraciones/s, 2 min por variante
#   RATE=60 DURATION=3m ./benchmark/run-ablation.sh
#   ONLY="completo" ./benchmark/run-ablation.sh     # repetir solo algunas variantes
set -euo pipefail

cd "$(dirname "$0")/.."
RESULTS=benchmark/results/ablation
export RATE="${RATE:-80}"
export DURATION="${DURATION:-2m}"
export CHAOS_FAILURE_RATE=0
mkdir -p "$RESULTS"
source benchmark/lib.sh

# etiqueta | variables de entorno de la variante
VARIANTS=(
  "baseline|OTEL_SDK_DISABLED=true"
  "instrumentacion-noop|OTEL_TRACES_EXPORTER=none OTEL_METRICS_EXPORTER=none OTEL_LOGS_EXPORTER=none"
  "solo-trazas|OTEL_METRICS_EXPORTER=none OTEL_LOGS_EXPORTER=none"
  "solo-metricas|OTEL_TRACES_EXPORTER=none OTEL_LOGS_EXPORTER=none"
  "solo-logs|OTEL_TRACES_EXPORTER=none OTEL_METRICS_EXPORTER=none"
  "completo|"
  "completo-muestreo-10|OTEL_TRACES_SAMPLER=parentbased_traceidratio OTEL_TRACES_SAMPLER_ARG=0.1"
)

for v in "${VARIANTS[@]}"; do
  label=${v%%|*}
  vars=${v#*|}
  if [[ -n "${ONLY:-}" && " $ONLY " != *" $label "* ]]; then continue; fi
  echo; echo "=================== Variante: $label ($vars) ==================="
  docker compose down -v --remove-orphans >/dev/null 2>&1 || true
  if [[ "$label" == "baseline" ]]; then
    env $vars docker compose up -d --build postgres service-b service-a
  else
    env OTEL_SDK_DISABLED=false $vars docker compose up -d --build
  fi
  wait_ready

  docker compose --profile loadtest run --rm -e RUN_LABEL="ablation/${label}-warmup" -e RATE="$RATE" -e DURATION=20s k6 >/dev/null

  sample_stats "$RESULTS/${label}-docker-stats.csv" &
  sampler=$!
  docker compose --profile loadtest run --rm -e RUN_LABEL="ablation/$label" -e RATE="$RATE" -e DURATION="$DURATION" k6 || true
  kill "$sampler" 2>/dev/null || true
  wait "$sampler" 2>/dev/null || true
done

python3 benchmark/analyze.py --ablation "$RESULTS"
OTEL_SDK_DISABLED=false docker compose up -d >/dev/null
echo; echo "Reporte: $RESULTS/ablation-report.md"
