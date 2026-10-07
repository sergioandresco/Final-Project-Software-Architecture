#!/usr/bin/env bash
# Ejecuta el mismo script k6 como Job dentro de GKE (evita la latencia de internet).
#   VUS=100 DURATION=5m RUN_LABEL=gke-otel ./run-k6-in-cluster.sh
set -euo pipefail
cd "$(dirname "$0")"
NAMESPACE=otel-lab
kubectl -n "$NAMESPACE" create configmap k6-script --from-file=../../benchmark/k6/load-test.js \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n "$NAMESPACE" delete job k6-load --ignore-not-found
cat <<YAML | kubectl -n "$NAMESPACE" apply -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: k6-load
spec:
  backoffLimit: 0
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: k6
          image: grafana/k6:2.3.0
          args: ["run", "/scripts/load-test.js"]
          env:
            - { name: BASE_URL, value: "http://service-a:8000" }
            - { name: VUS, value: "${VUS:-100}" }
            - { name: DURATION, value: "${DURATION:-5m}" }
            - { name: RUN_LABEL, value: "${RUN_LABEL:-gke}" }
          volumeMounts:
            - { name: script, mountPath: /scripts }
            - { name: results, mountPath: /results }
      volumes:
        - name: script
          configMap:
            name: k6-script
        - name: results
          emptyDir: {}
YAML
kubectl -n "$NAMESPACE" wait --for=condition=ready pod -l job-name=k6-load --timeout=120s || true
kubectl -n "$NAMESPACE" logs -f job/k6-load
