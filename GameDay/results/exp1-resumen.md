| Fase | req/s | p99 POST /api/orders (depende de B) | p99 GET /api/catalog (depende de B) | p99 GET /api/orders (no depende de B) | Solicitudes concurrentes (máx) | CPU service-a | Errores 5xx (máx) |
|---|---|---|---|---|---|---|---|
| Estado estable | 66.7 | 25 ms | 23 ms | 43 ms | 0 | 25% | 0.00% |
| Latencia +100ms | 44.8 | 250 ms | 249 ms | 23 ms | 8 | 23% | 0.00% |
| Latencia +400ms | 65.8 | 679 ms | 981 ms | 45 ms | 25 | 28% | 0.06% |
| Latencia +1000ms | 49.6 | 3092 ms | 2953 ms | 2401 ms | 293 | 24% | 0.10% |
| Recuperación | 57.1 | 44 ms | 21 ms | 25 ms | 1 | 22% | 0.00% |
