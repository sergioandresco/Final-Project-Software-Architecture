# Funciones comunes de los scripts de benchmark (se cargan con `source`).

wait_ready() {
  echo "Esperando a que service-a esté listo..."
  for _ in $(seq 1 60); do
    if curl -fsS http://localhost:8000/health/ready >/dev/null 2>&1; then return 0; fi
    sleep 2
  done
  echo "service-a no respondió a tiempo" >&2
  exit 1
}

sample_stats() {
  # $1 = archivo CSV de salida; muestrea hasta que el proceso padre lo mate.
  local out=$1
  echo "timestamp,container,cpu_percent,mem_mib" > "$out"
  while true; do
    local ids
    ids=$(docker compose ps -q service-a service-b otel-collector 2>/dev/null | tr '\n' ' ')
    docker stats --no-stream --format '{{.Name}},{{.CPUPerc}},{{.MemUsage}}' $ids 2>/dev/null |
      while IFS=, read -r name cpu mem; do
        local mib
        mib=$(echo "$mem" | awk '{v=$1; if (v ~ /GiB/) {sub(/GiB/,"",v); v=v*1024} else if (v ~ /KiB/) {sub(/KiB/,"",v); v=v/1024} else {sub(/MiB/,"",v)}; print v}')
        echo "$(date +%s),${name},${cpu%\%},${mib}" >> "$out"
      done
  done
}
