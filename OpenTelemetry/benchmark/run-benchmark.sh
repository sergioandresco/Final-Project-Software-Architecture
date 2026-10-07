#!/usr/bin/env bash
# Benchmark de overhead: misma carga k6 contra el stack en tres modos:
#   baseline      sin instrumentación (OTEL_SDK_DISABLED=true, sin Collector)
#   otel          instrumentación completa, muestreo 100%
#   otel-sampled  instrumentación completa, muestreo head-based 10%
# Muestrea CPU/memoria con `docker stats` y genera benchmark/results/overhead-report.md.
#
# Uso (desde OpenTelemetry/):
#   ./benchmark/run-benchmark.sh                    # 3 corridas de 100 VUs × 5 minutos
#   VUS=50 DURATION=5m ./benchmark/run-benchmark.sh
#   CASES="otel-sampled" ./benchmark/run-benchmark.sh   # repetir solo un caso
set -euo pipefail

cd "$(dirname "$0")/.."
RESULTS=benchmark/results
export VUS="${VUS:-100}"
export DURATION="${DURATION:-5m}"
export CHAOS_FAILURE_RATE=0   # sin fallas inyectadas: solo medimos overhead
mkdir -p "$RESULTS"

source benchmark/lib.sh

run_case() {
  local label=$1
  echo; echo "=================== Corrida: $label ==================="
  docker compose down -v --remove-orphans >/dev/null 2>&1 || true

  case "$label" in
    baseline)
      OTEL_SDK_DISABLED=true docker compose up -d --build postgres service-b service-a ;;
    otel)
      OTEL_SDK_DISABLED=false docker compose up -d --build ;;
    otel-sampled)
      OTEL_SDK_DISABLED=false OTEL_TRACES_SAMPLER=parentbased_traceidratio OTEL_TRACES_SAMPLER_ARG=0.1 \
        docker compose up -d --build ;;
    *) echo "Caso desconocido: $label" >&2; exit 1 ;;
  esac
  wait_ready

  echo "Warm-up (30s, 20 VUs)..."
  docker compose --profile loadtest run --rm -e RUN_LABEL="${label}-warmup" -e VUS=20 -e DURATION=30s k6 >/dev/null

  sample_stats "$RESULTS/${label}-docker-stats.csv" &
  local sampler=$!
  docker compose --profile loadtest run --rm -e RUN_LABEL="$label" -e VUS="$VUS" -e DURATION="$DURATION" k6 || true
  kill "$sampler" 2>/dev/null || true
  wait "$sampler" 2>/dev/null || true
}

for c in ${CASES:-baseline otel otel-sampled}; do
  run_case "$c"
done

# Deja el stack instrumentado con la configuración por defecto (muestreo 100%) para tomar evidencias.
OTEL_SDK_DISABLED=false docker compose up -d >/dev/null

python3 benchmark/analyze.py "$RESULTS"
echo; echo "Reporte: $RESULTS/overhead-report.md"
echo "El stack instrumentado queda arriba para revisar Grafana/Jaeger. Para apagarlo: docker compose down -v"
