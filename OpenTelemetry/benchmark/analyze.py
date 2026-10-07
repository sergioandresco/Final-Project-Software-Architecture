"""Genera las tablas de overhead a partir de los resúmenes JSON de k6 y los CSV de `docker stats`.

  python3 benchmark/analyze.py [results]               # baseline vs. OTel 100% vs. OTel 10%
  python3 benchmark/analyze.py --ablation [results]    # costo por componente a tasa fija
"""

import csv
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path


def k6_metrics(path: Path) -> dict:
    m = json.loads(path.read_text())["metrics"]
    d = m["http_req_duration"]["values"]
    return {
        "p50": d["med"],
        "p95": d["p(95)"],
        "p99": d["p(99)"],
        "avg": d["avg"],
        "rps": m["http_reqs"]["values"]["rate"],
        "requests": m["http_reqs"]["values"]["count"],
        "errors": m["http_req_failed"]["values"]["rate"] * 100,
    }


def docker_stats(path: Path) -> dict:
    rows = defaultdict(lambda: {"cpu": [], "mem": []})
    with path.open() as f:
        for r in csv.DictReader(f):
            key = next((s for s in ("service-a", "service-b", "otel-collector") if s in r["container"]), None)
            if key is None:
                continue
            try:
                rows[key]["cpu"].append(float(r["cpu_percent"]))
                rows[key]["mem"].append(float(r["mem_mib"]))
            except ValueError:
                continue
    out = {}
    for key, v in rows.items():
        cpu = sorted(v["cpu"])
        out[key] = {
            "cpu_avg": statistics.mean(cpu),
            "cpu_median": statistics.median(cpu),
            # Fracción de muestras con el servicio saturado (>= 90% de su único core).
            "saturated": sum(c >= 90 for c in cpu) / len(cpu) * 100,
            "cpu_p95": cpu[int(0.95 * (len(cpu) - 1))],
            "mem_avg": statistics.mean(v["mem"]),
            "mem_max": max(v["mem"]),
        }
    return out


def steady_cpu(path: Path) -> tuple[float, float]:
    """Mediana de CPU de service-a y service-b excluyendo los instantes con service-a saturado (>= 90%)."""
    by_ts = defaultdict(dict)
    with path.open() as f:
        for r in csv.DictReader(f):
            for svc in ("service-a", "service-b"):
                if svc in r["container"]:
                    by_ts[r["timestamp"]][svc] = float(r["cpu_percent"])
    pairs = [(v["service-a"], v["service-b"]) for v in by_ts.values() if len(v) == 2 and v["service-a"] < 90]
    return statistics.median(p[0] for p in pairs), statistics.median(p[1] for p in pairs)


def pct(base: float, new: float) -> str:
    return f"{(new - base) / base * 100:+.1f}%" if base else "n/a"


CASES = [
    ("otel", "OTel 100%"),
    ("otel-sampled", "OTel 10% muestreo"),
]


def main(results: Path) -> None:
    kb, sb = k6_metrics(results / "baseline-k6-summary.json"), docker_stats(results / "baseline-docker-stats.csv")
    cases = [
        (label, title, k6_metrics(results / f"{label}-k6-summary.json"), docker_stats(results / f"{label}-docker-stats.csv"))
        for label, title in CASES
        if (results / f"{label}-k6-summary.json").exists()
    ]

    def row(name, getter):
        b = getter(kb, sb)
        cells = [f"{b:.2f}"]
        for _, _, k, st in cases:
            v = getter(k, st)
            cells += [f"{v:.2f}", pct(b, v)]
        return f"| {name} | " + " | ".join(cells) + " |"

    header = "| Métrica | Sin OTel (baseline) | " + " | ".join(f"{t} | Δ %" for _, t, _, _ in cases) + " |"
    lines = [
        "# Análisis de overhead — OpenTelemetry",
        "",
        "Carga: k6 constant-vus. Requests totales: baseline "
        + f"{int(kb['requests'])}"
        + "".join(f", {t} {int(k['requests'])}" for _, t, k, _ in cases)
        + ".",
        "",
        header,
        "|---|---:|" + "---:|---:|" * len(cases),
        row("Latencia p50 (ms)", lambda k, st: k["p50"]),
        row("Latencia p95 (ms)", lambda k, st: k["p95"]),
        row("**Latencia p99 (ms)**", lambda k, st: k["p99"]),
        row("Latencia promedio (ms)", lambda k, st: k["avg"]),
        row("Throughput (req/s)", lambda k, st: k["rps"]),
        row("Tasa de error (%)", lambda k, st: k["errors"]),
    ]
    for svc in ("service-a", "service-b"):
        lines += [
            row(f"**CPU {svc} promedio (%)**", lambda k, st, svc=svc: st[svc]["cpu_avg"]),
            row(f"CPU {svc} p95 (%)", lambda k, st, svc=svc: st[svc]["cpu_p95"]),
            row(f"**Memoria {svc} promedio (MiB)**", lambda k, st, svc=svc: st[svc]["mem_avg"]),
            row(f"Memoria {svc} máx (MiB)", lambda k, st, svc=svc: st[svc]["mem_max"]),
        ]

    def total(st, key):
        return st["service-a"][key] + st["service-b"][key]

    lines += ["", "## Resumen", ""]
    for _, title, k, st in cases:
        lines += [
            f"### {title}",
            "",
            f"- **Latencia adicional p99:** {k['p99'] - kb['p99']:+.2f} ms ({pct(kb['p99'], k['p99'])})",
            f"- **CPU overhead (service-a + service-b):** {total(st, 'cpu_avg') - total(sb, 'cpu_avg'):+.2f} puntos "
            f"({pct(total(sb, 'cpu_avg'), total(st, 'cpu_avg'))})",
            f"- **Memoria adicional (service-a + service-b):** {total(st, 'mem_avg') - total(sb, 'mem_avg'):+.2f} MiB "
            f"({pct(total(sb, 'mem_avg'), total(st, 'mem_avg'))})",
        ]
        if "otel-collector" in st:
            c = st["otel-collector"]
            lines.append(
                f"- **Costo del OTel Collector (fuera del proceso):** CPU promedio {c['cpu_avg']:.2f}% · "
                f"memoria promedio {c['mem_avg']:.1f} MiB (máx {c['mem_max']:.1f} MiB)"
            )
        lines.append("")
    lines += ["> CPU expresada como % de un core según `docker stats` (cada servicio limitado a 1 CPU / 512 MiB)."]

    out = results / "overhead-report.md"
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


ABLATION = [
    ("baseline", "Sin OTel (SDK deshabilitado)"),
    ("instrumentacion-noop", "Instrumentación con API no-op (sin providers)"),
    ("solo-trazas", "Solo trazas (100%)"),
    ("solo-metricas", "Solo métricas"),
    ("solo-logs", "Solo logs OTLP"),
    ("completo", "Completo (trazas 100% + métricas + logs)"),
    ("completo-muestreo-10", "Completo con muestreo 10%"),
]


def ablation(results: Path) -> None:
    rows = []
    for label, title in ABLATION:
        if not (results / f"{label}-k6-summary.json").exists():
            continue
        k = k6_metrics(results / f"{label}-k6-summary.json")
        st = docker_stats(results / f"{label}-docker-stats.csv")
        a_med, b_med = steady_cpu(results / f"{label}-docker-stats.csv")
        a, b = st["service-a"], st["service-b"]
        rows.append({
            "title": title, "k": k, "a_med": a_med, "b_med": b_med,
            "steady": (a_med + b_med) / 100 / k["rps"] * 1000,
            "avg": (a["cpu_avg"] + b["cpu_avg"]) / 100 / k["rps"] * 1000,
            "saturated": a["saturated"], "mem": a["mem_avg"] + b["mem_avg"],
        })

    base = rows[0]
    lines = [
        "# Overhead por componente (ablación a tasa fija)",
        "",
        f"Carga: k6 constant-arrival-rate, misma tasa en todas las variantes ({base['k']['rps']:.1f} req/s medidos en baseline).",
        "",
        "- **CPU/req estable** = (mediana CPU service-a + mediana CPU service-b) / req/s, excluyendo los instantes",
        "  con service-a saturado: es el costo intrínseco de la instrumentación.",
        "- **CPU/req promedio** usa la media de toda la corrida e incluye los episodios de saturación.",
        "- **% saturado** = muestras con service-a >= 90% de su core (episodios metaestables: cola + contención del GIL).",
        "",
        "| Variante | req/s | p50 (ms) | p99 (ms) | CPU a (%) | CPU b (%) | CPU/req estable (ms) | Δ vs baseline | CPU/req promedio (ms) | % saturado | Memoria a+b (MiB) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        k = r["k"]
        lines.append(
            f"| {r['title']} | {k['rps']:.1f} | {k['p50']:.1f} | {k['p99']:.1f} | {r['a_med']:.1f} | {r['b_med']:.1f} | "
            f"{r['steady']:.2f} | {r['steady'] - base['steady']:+.2f} ms ({pct(base['steady'], r['steady'])}) | "
            f"{r['avg']:.2f} | {r['saturated']:.0f}% | {r['mem']:.1f} |"
        )
    lines += ["", "> CPU expresada como % de un core según `docker stats` (muestreo cada ~2 s); columnas CPU a/b = mediana en estado estable."]
    out = results / "ablation-report.md"
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--ablation":
        ablation(Path(args[1] if len(args) > 1 else "benchmark/results/ablation"))
    else:
        main(Path(args[0] if args else "benchmark/results"))
