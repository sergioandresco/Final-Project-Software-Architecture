# Overhead por componente (ablación a tasa fija)

Carga: k6 constant-arrival-rate, misma tasa en todas las variantes (89.8 req/s medidos en baseline).

- **CPU/req estable** = (mediana CPU service-a + mediana CPU service-b) / req/s, excluyendo los instantes
  con service-a saturado: es el costo intrínseco de la instrumentación.
- **CPU/req promedio** usa la media de toda la corrida e incluye los episodios de saturación.
- **% saturado** = muestras con service-a >= 90% de su core (episodios metaestables: cola + contención del GIL).

| Variante | req/s | p50 (ms) | p99 (ms) | CPU a (%) | CPU b (%) | CPU/req estable (ms) | Δ vs baseline | CPU/req promedio (ms) | % saturado | Memoria a+b (MiB) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Sin OTel (SDK deshabilitado) | 89.8 | 4.6 | 60.2 | 16.3 | 12.0 | 3.15 | +0.00 ms (+0.0%) | 3.30 | 0% | 128.3 |
| Instrumentación con API no-op (sin providers) | 86.5 | 6.2 | 2120.6 | 22.1 | 16.1 | 4.42 | +1.27 ms (+40.3%) | 8.04 | 16% | 159.1 |
| Solo trazas (100%) | 89.5 | 6.3 | 315.2 | 28.9 | 22.1 | 5.70 | +2.55 ms (+81.2%) | 6.33 | 2% | 164.6 |
| Solo métricas | 90.0 | 5.5 | 380.3 | 21.7 | 15.9 | 4.18 | +1.03 ms (+32.9%) | 4.78 | 2% | 157.2 |
| Solo logs OTLP | 89.6 | 5.4 | 90.4 | 20.6 | 15.5 | 4.03 | +0.88 ms (+28.0%) | 4.43 | 0% | 152.2 |
| Completo (trazas 100% + métricas + logs) | 89.0 | 22.1 | 1718.7 | 41.7 | 31.3 | 8.21 | +5.06 ms (+160.9%) | 11.98 | 29% | 172.8 |
| Completo con muestreo 10% | 89.5 | 7.1 | 937.0 | 30.4 | 22.3 | 5.89 | +2.74 ms (+87.2%) | 6.68 | 2% | 163.9 |

> CPU expresada como % de un core según `docker stats` (muestreo cada ~2 s); columnas CPU a/b = mediana en estado estable.
