#!/usr/bin/env bash
# Game Day · Experimento 1: latencia de red entre service-a y service-b (tc netem)
#
# Hipótesis H1: en estado estable (~50 iteraciones/s, errores < 2%, p99 < 500 ms), cuando la red
# service-b → service-a agrega latencia (100 → 400 → 1000 ms), esperamos que service-a absorba la
# demora sin errores (timeout de 5 s hacia service-b) y que solo se degraden las rutas que dependen
# de service-b; GET /api/orders (no depende de service-b) debe mantenerse estable.
#
# Radio de impacto: solo el tráfico service-b → service-a (filtro tc u32 por IP destino). La base de
# datos, el Collector y el resto de contenedores no se afectan.
# Rollback automático: `tc qdisc del dev eth0 root` al terminar, ante error, Ctrl-C o condición de aborto.
#
# Requisitos: stack de OpenTelemetry/ arriba (docker compose up -d) y Docker con la red
# opentelemetry_default.
#
# Uso (desde la raíz del repo):
#   ./GameDay/chaos/exp1-latencia-red.sh
#   PHASES="100 400" PHASE_SECONDS=60 ./GameDay/chaos/exp1-latencia-red.sh     # versión corta
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OTEL="$ROOT/OpenTelemetry"
RESULTS="$ROOT/GameDay/results"
PROM="http://localhost:9090"

PHASES="${PHASES:-100 400 1000}"          # ms de latencia por fase (escalamiento gradual)
JITTER_PCT="${JITTER_PCT:-10}"            # jitter = 10% de la latencia
BASELINE_SECONDS="${BASELINE_SECONDS:-120}"
PHASE_SECONDS="${PHASE_SECONDS:-120}"
RECOVERY_SECONDS="${RECOVERY_SECONDS:-120}"
RATE="${RATE:-50}"                        # iteraciones/s de k6 (carga abierta: no baja si el sistema se pone lento)
ABORT_ERROR_PCT="${ABORT_ERROR_PCT:-5}"   # aborta si los 5xx de service-a superan este %
ABORT_P99_SECONDS="${ABORT_P99_SECONDS:-5}"   # aborta si el p99 de service-a supera este valor
NETSHOOT="nicolaka/netshoot:latest"
B_CONTAINER="opentelemetry-service-b-1"
A_CONTAINER="opentelemetry-service-a-1"

mkdir -p "$RESULTS"
TIMELINE="$RESULTS/exp1-timeline.csv"
EVENTS="$RESULTS/exp1-eventos.log"
: > "$EVENTS"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$EVENTS"; }
netns() { docker run --rm --net "container:$B_CONTAINER" --cap-add NET_ADMIN "$NETSHOOT" "$@"; }

# ---------- Consultas a Prometheus ----------
promq() {  # $1 = PromQL -> valor escalar (o "nan")
  curl -fsG "$PROM/api/v1/query" --data-urlencode "query=$1" |
    python3 -c 'import sys,json; r=json.load(sys.stdin)["data"]["result"]; print(r[0]["value"][1] if r else "nan")'
}
SVC='service_name="service-a"'
Q_RPS="sum(rate(http_server_request_duration_seconds_count{$SVC}[30s]))"
Q_ERR="100 * (sum(rate(http_server_request_duration_seconds_count{$SVC,http_response_status_code=~\"5..\"}[30s])) or vector(0)) / sum(rate(http_server_request_duration_seconds_count{$SVC}[30s]))"
q_p99() { echo "histogram_quantile(0.99, sum by (le) (rate(http_server_request_duration_seconds_bucket{$SVC$1}[30s])))"; }
Q_ACTIVE="sum(http_server_active_requests{$SVC})"

# ---------- Rollback automático ----------
INJECTED=0
rollback() {
  if [[ $INJECTED -eq 1 ]]; then
    netns tc qdisc del dev eth0 root 2>/dev/null || true
    INJECTED=0
    log "ROLLBACK: tc qdisc eliminado; red de service-b restaurada"
  fi
}
cleanup() {
  rollback
  docker rm -f gameday-k6 >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

inject() {  # $1 = latencia en ms
  local ms=$1 jitter=$(( $1 * JITTER_PCT / 100 ))
  netns tc qdisc del dev eth0 root 2>/dev/null || true
  netns sh -c "tc qdisc add dev eth0 root handle 1: prio &&
    tc qdisc add dev eth0 parent 1:3 handle 30: netem delay ${ms}ms ${jitter}ms &&
    tc filter add dev eth0 protocol ip parent 1:0 prio 3 u32 match ip dst ${A_IP}/32 flowid 1:3"
  INJECTED=1
  log "INYECCIÓN: netem delay ${ms}ms ±${jitter}ms en service-b → service-a (${A_IP})"
}

# Mide durante $2 segundos, cada 10 s. Con $3=1 (por defecto) evalúa las condiciones de aborto;
# en la recuperación se pasa 0: solo se observa cuánto tarda en volver al estado estable.
observe() {  # $1 = fase, $2 = segundos, $3 = evaluar aborto (1/0)
  local phase=$1 until=$(( $(date +%s) + $2 )) check=${3:-1}
  while [[ $(date +%s) -lt $until ]]; do
    sleep 10
    local rps err p99 p99dep p99indep active
    rps=$(promq "$Q_RPS"); err=$(promq "$Q_ERR"); p99=$(promq "$(q_p99 '')")
    p99dep=$(promq "$(q_p99 ',http_route="/api/orders",http_request_method="POST"')")
    p99indep=$(promq "$(q_p99 ',http_route="/api/orders",http_request_method="GET"')")
    active=$(promq "$Q_ACTIVE")
    echo "$(date +%s),$phase,$rps,$err,$p99,$p99dep,$p99indep,$active" >> "$TIMELINE"
    printf '  %-10s rps=%6.1f  err=%5.2f%%  p99=%6.3fs  p99 POST=%6.3fs  p99 GET(indep)=%6.3fs  activas=%s\n' \
      "$phase" "$rps" "$err" "$p99" "$p99dep" "$p99indep" "$active" | tee -a "$EVENTS"
    if [[ $check -eq 1 ]] && python3 -c "import sys; e,p=float('$err'),float('$p99'); sys.exit(0 if (e>$ABORT_ERROR_PCT or p>$ABORT_P99_SECONDS) else 1)" 2>/dev/null; then
      log "ABORTO: condición de aborto alcanzada en fase $phase (err=${err}% p99=${p99}s)"
      return 1
    fi
  done
}

# ================= 0. Preparación =================
log "Preparación: service-b sin fallas inyectadas (CHAOS_FAILURE_RATE=0) para aislar el efecto de la latencia"
(cd "$OTEL" && CHAOS_FAILURE_RATE=0 docker compose up -d service-b service-a >/dev/null 2>&1)
for _ in $(seq 1 60); do curl -fs localhost:8000/health/ready >/dev/null && break; sleep 2; done
docker pull -q "$NETSHOOT" >/dev/null
A_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$A_CONTAINER")
netns tc qdisc del dev eth0 root 2>/dev/null || true
echo "ts,fase,rps,error_pct,p99_s,p99_post_orders_s,p99_get_orders_s,activas" > "$TIMELINE"

log "Carga: k6 constant-arrival-rate ${RATE} it/s"
TOTAL=$(( BASELINE_SECONDS + PHASE_SECONDS * $(wc -w <<< "$PHASES") + RECOVERY_SECONDS + 30 ))
docker run -d --name gameday-k6 --network opentelemetry_default \
  -v "$OTEL/benchmark/k6:/scripts:ro" -v "$RESULTS:/results" \
  -e BASE_URL=http://service-a:8000 -e RATE="$RATE" -e VUS=300 -e DURATION="${TOTAL}s" -e RUN_LABEL=exp1-k6 \
  grafana/k6:2.3.0 run /scripts/load-test.js >/dev/null

# ================= 1. Estado estable =================
log "FASE baseline (${BASELINE_SECONDS}s): verificación del estado estable"
sleep 20   # deja que las métricas reflejen la carga
observe baseline "$BASELINE_SECONDS" || exit 1
ERR0=$(promq "$Q_ERR"); P990=$(promq "$(q_p99 '')")
if ! python3 -c "import sys; sys.exit(0 if float('$ERR0')<2 and float('$P990')<0.5 else 1)"; then
  log "Estado estable NO verificado (err=${ERR0}% p99=${P990}s): se cancela sin inyectar"
  exit 1
fi
log "Estado estable verificado: err=${ERR0}% p99=${P990}s"

# ================= 2. Inyección escalonada =================
ABORTED=0
for ms in $PHASES; do
  inject "$ms"
  TID=$(curl -s -X POST localhost:8000/api/orders -H 'content-type: application/json' \
    -d '{"customer_id":"gameday","product_id":7,"quantity":1}' | python3 -c 'import sys,json; print(json.load(sys.stdin).get("trace_id"))' 2>/dev/null || echo "?")
  log "Traza de ejemplo en fase ${ms}ms: $TID  (http://localhost:16686/trace/$TID)"
  if ! observe "${ms}ms" "$PHASE_SECONDS"; then ABORTED=1; break; fi
done

# ================= 3. Rollback y recuperación =================
rollback
log "FASE recuperación (${RECOVERY_SECONDS}s)"
observe recuperacion "$RECOVERY_SECONDS" 0
# SIGINT hace que k6 termine de forma ordenada e imprima su resumen.
docker kill -s INT gameday-k6 >/dev/null 2>&1 || true
docker wait gameday-k6 >/dev/null 2>&1 || true
docker logs gameday-k6 2>&1 | grep -v -E "^running|^steady_load|^$" > "$RESULTS/exp1-k6.log" || true
docker rm -f gameday-k6 >/dev/null 2>&1 || true

[[ $ABORTED -eq 1 ]] && log "Resultado: experimento ABORTADO por condición de seguridad" || log "Resultado: experimento completado"
log "Timeline: $TIMELINE"
