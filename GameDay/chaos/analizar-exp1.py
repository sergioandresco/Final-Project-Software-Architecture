"""Analiza el experimento 1 (latencia de red) a partir de Prometheus.

Lee las fases desde results/exp1-timeline.csv, consulta Prometheus para todo el intervalo del
experimento y genera:
  * results/exp1-grafica.png   latencia p99 por ruta, solicitudes concurrentes y errores por fase
  * results/exp1-resumen.md    tabla resumen por fase

Requisitos: el stack de OpenTelemetry/ arriba (Prometheus en :9090) y `pip install matplotlib`.

    python3 GameDay/chaos/analizar-exp1.py
"""

import csv
import json
import statistics
import urllib.parse
import urllib.request
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.dates import DateFormatter  # noqa: E402
from datetime import datetime  # noqa: E402

RESULTS = Path(__file__).resolve().parents[1] / "results"
PROM = "http://localhost:9090"
SVC = 'service_name="service-a"'
STEP = 5
# Se excluye el primer minuto: calentamiento de conexiones tras recrear los contenedores (no es estado estable).
WARMUP_SECONDS = 90

QUERIES = {
    "p99_post": f'histogram_quantile(0.99, sum by (le) (rate(http_server_request_duration_seconds_bucket{{{SVC},http_route="/api/orders",http_request_method="POST"}}[30s])))',
    "p99_catalog": f'histogram_quantile(0.99, sum by (le) (rate(http_server_request_duration_seconds_bucket{{{SVC},http_route="/api/catalog"}}[30s])))',
    "p99_get_indep": f'histogram_quantile(0.99, sum by (le) (rate(http_server_request_duration_seconds_bucket{{{SVC},http_route="/api/orders",http_request_method="GET"}}[30s])))',
    "activas": f"sum(http_server_active_requests{{{SVC}}})",
    "rps": f"sum(rate(http_server_request_duration_seconds_count{{{SVC}}}[30s]))",
    "error_pct": f'100 * (sum(rate(http_server_request_duration_seconds_count{{{SVC},http_response_status_code=~"5.."}}[30s])) or vector(0)) / sum(rate(http_server_request_duration_seconds_count{{{SVC}}}[30s]))',
    "cpu_a": 'sum(rate(process_cpu_time_seconds_total{service_name="service-a"}[30s])) * 100',
}

PHASE_LABEL = {"baseline": "Estado estable", "recuperacion": "Recuperación"}
PHASE_COLOR = {"100ms": "#fde9c9", "400ms": "#fbcf8f", "1000ms": "#f6a96b"}


def query_range(q: str, start: float, end: float) -> list[tuple[float, float]]:
    url = f"{PROM}/api/v1/query_range?" + urllib.parse.urlencode({"query": q, "start": start, "end": end, "step": STEP})
    data = json.load(urllib.request.urlopen(url))["data"]["result"]
    if not data:
        return []
    return [(float(t), float(v)) for t, v in data[0]["values"] if v not in ("NaN", "+Inf")]


def phases() -> list[tuple[str, float, float]]:
    rows = list(csv.DictReader((RESULTS / "exp1-timeline.csv").open()))
    order, spans = [], {}
    for r in rows:
        ts, f = float(r["ts"]), r["fase"]
        if f not in spans:
            order.append(f)
            spans[f] = [ts - 10, ts]  # cada muestra cubre los 10 s anteriores
        spans[f][1] = ts
    out = [(f, spans[f][0], spans[f][1]) for f in order]
    f0, a0, b0 = out[0]
    out[0] = (f0, a0 + WARMUP_SECONDS, b0)
    return out


def main() -> None:
    ph = phases()
    start, end = ph[0][1], ph[-1][2]
    series = {k: query_range(q, start, end) for k, q in QUERIES.items()}

    # ---------- Tabla resumen ----------
    def in_phase(key, a, b, fn):
        vals = [v for t, v in series[key] if a + 30 <= t <= b]  # descarta los primeros 30 s (ventana de rate)
        vals = vals or [v for t, v in series[key] if a <= t <= b]
        return fn(vals) if vals else float("nan")

    lines = [
        "| Fase | req/s | p99 POST /api/orders (depende de B) | p99 GET /api/catalog (depende de B) | p99 GET /api/orders (no depende de B) | Solicitudes concurrentes (máx) | CPU service-a | Errores 5xx (máx) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for f, a, b in ph:
        name = PHASE_LABEL.get(f, f"Latencia +{f}")
        lines.append(
            f"| {name} | {in_phase('rps', a, b, statistics.median):.1f} "
            f"| {in_phase('p99_post', a, b, statistics.median) * 1000:.0f} ms "
            f"| {in_phase('p99_catalog', a, b, statistics.median) * 1000:.0f} ms "
            f"| {in_phase('p99_get_indep', a, b, statistics.median) * 1000:.0f} ms "
            f"| {in_phase('activas', a, b, max):.0f} "
            f"| {in_phase('cpu_a', a, b, statistics.median):.0f}% "
            f"| {in_phase('error_pct', a, b, max):.2f}% |"
        )
    (RESULTS / "exp1-resumen.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))

    # ---------- Gráfica ----------
    plt.rcParams.update({"font.size": 9, "font.family": "Arial"})
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8.2, 5.6), sharex=True, gridspec_kw={"height_ratios": [3, 2]})
    t = lambda s: [datetime.fromtimestamp(x) for x, _ in s]  # noqa: E731
    v = lambda s, k=1: [y * k for _, y in s]  # noqa: E731

    ax1.plot(t(series["p99_post"]), v(series["p99_post"], 1000), color="#0A2C52", lw=1.6, label="POST /api/orders (llama a service-b)")
    ax1.plot(t(series["p99_catalog"]), v(series["p99_catalog"], 1000), color="#2E86DE", lw=1.2, ls="--", label="GET /api/catalog (llama a service-b)")
    ax1.plot(t(series["p99_get_indep"]), v(series["p99_get_indep"], 1000), color="#C0392B", lw=1.6, label="GET /api/orders (NO llama a service-b)")
    ax1.set_ylabel("Latencia p99 (ms)")
    ax1.set_yscale("log")
    ax1.legend(loc="upper left", bbox_to_anchor=(0.0, 0.9), fontsize=8, frameon=False)
    ax1.grid(alpha=0.25)

    ax2.plot(t(series["activas"]), v(series["activas"]), color="#6C3483", lw=1.4, label="Solicitudes concurrentes en service-a")
    ax2.axhline(40, color="#6C3483", ls=":", lw=1)
    ax2.text(datetime.fromtimestamp(start + 5), 41, "límite del grupo de hilos (40)", color="#6C3483", fontsize=7.5)
    ax2.set_ylabel("Concurrentes")
    ax2.grid(alpha=0.25)
    ax2b = ax2.twinx()
    ax2b.plot(t(series["error_pct"]), v(series["error_pct"]), color="#E67E22", lw=1.2, label="Errores 5xx (%)")
    ax2b.set_ylabel("Errores 5xx (%)", color="#E67E22")
    h1, l1 = ax2.get_legend_handles_labels()
    h2, l2 = ax2b.get_legend_handles_labels()
    ax2.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=8, frameon=False)

    for f, a, b in ph:
        for ax in (ax1, ax2):
            ax.axvspan(datetime.fromtimestamp(a), datetime.fromtimestamp(b), color=PHASE_COLOR.get(f, "#ffffff"), alpha=0.6, lw=0)
        ax1.text(datetime.fromtimestamp((a + b) / 2), ax1.get_ylim()[1] * 0.75, PHASE_LABEL.get(f, f"+{f}"),
                 ha="center", fontsize=7.5, color="#333")
    ax2.xaxis.set_major_formatter(DateFormatter("%H:%M"))
    fig.tight_layout()
    fig.savefig(RESULTS / "exp1-grafica.png", dpi=200)
    print(f"Gráfica: {RESULTS / 'exp1-grafica.png'}")


if __name__ == "__main__":
    main()
