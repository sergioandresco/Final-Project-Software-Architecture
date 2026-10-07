# Análisis de overhead — OpenTelemetry

Carga: k6 constant-vus. Requests totales: baseline 62129, OTel 100% 44845, OTel 10% muestreo 37166.

| Métrica | Sin OTel (baseline) | OTel 100% | Δ % | OTel 10% muestreo | Δ % |
|---|---:|---:|---:|---:|---:|
| Latencia p50 (ms) | 7.30 | 123.67 | +1593.4% | 157.62 | +2058.3% |
| Latencia p95 (ms) | 146.35 | 751.14 | +413.3% | 1216.76 | +731.4% |
| **Latencia p99 (ms)** | 445.90 | 1263.60 | +183.4% | 3587.06 | +704.4% |
| Latencia promedio (ms) | 29.64 | 213.57 | +620.4% | 346.83 | +1070.0% |
| Throughput (req/s) | 210.32 | 151.42 | -28.0% | 125.53 | -40.3% |
| Tasa de error (%) | 0.01 | 0.00 | -100.0% | 0.01 | -25.7% |
| **CPU service-a promedio (%)** | 53.42 | 96.91 | +81.4% | 98.25 | +83.9% |
| CPU service-a p95 (%) | 94.21 | 104.23 | +10.6% | 110.52 | +17.3% |
| **Memoria service-a promedio (MiB)** | 73.18 | 95.44 | +30.4% | 93.16 | +27.3% |
| Memoria service-a máx (MiB) | 75.20 | 96.94 | +28.9% | 95.69 | +27.2% |
| **CPU service-b promedio (%)** | 35.83 | 64.93 | +81.3% | 62.84 | +75.4% |
| CPU service-b p95 (%) | 59.86 | 77.82 | +30.0% | 80.25 | +34.1% |
| **Memoria service-b promedio (MiB)** | 64.53 | 83.45 | +29.3% | 80.90 | +25.4% |
| Memoria service-b máx (MiB) | 65.88 | 85.43 | +29.7% | 82.87 | +25.8% |

## Resumen

### OTel 100%

- **Latencia adicional p99:** +817.69 ms (+183.4%)
- **CPU overhead (service-a + service-b):** +72.60 puntos (+81.3%)
- **Memoria adicional (service-a + service-b):** +41.19 MiB (+29.9%)
- **Costo del OTel Collector (fuera del proceso):** CPU promedio 6.57% · memoria promedio 85.2 MiB (máx 90.7 MiB)

### OTel 10% muestreo

- **Latencia adicional p99:** +3141.16 ms (+704.4%)
- **CPU overhead (service-a + service-b):** +71.84 puntos (+80.5%)
- **Memoria adicional (service-a + service-b):** +36.35 MiB (+26.4%)
- **Costo del OTel Collector (fuera del proceso):** CPU promedio 5.18% · memoria promedio 80.9 MiB (máx 88.1 MiB)

> CPU expresada como % de un core según `docker stats` (cada servicio limitado a 1 CPU / 512 MiB).
