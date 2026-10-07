"""Genera docs/reporte-tecnico.pdf a partir de docs/reporte-tecnico.md con el formato de los
informes de la materia (portada Universidad de La Sabana, tablas y figuras APA, fuente Aptos).

Requisitos: `pip install markdown` y Google Chrome (se imprime en modo headless; así el diagrama
Mermaid se renderiza igual que en GitHub). Usa las fuentes Aptos/Arial que trae Microsoft Office
si están instaladas; si no, cae en Helvetica.

    python3 docs/build-pdf.py
"""

import re
import subprocess
from pathlib import Path

import markdown

DOCS = Path(__file__).resolve().parent
SRC = DOCS / "reporte-tecnico.md"
HTML = DOCS / "reporte-tecnico.html"
PDF = DOCS / "reporte-tecnico.pdf"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
OFFICE_FONTS = Path("/Applications/Microsoft Outlook.app/Contents/Resources/DFonts")

# --- Datos de la portada -------------------------------------------------------------------
UNIVERSIDAD = "UNIVERSIDAD DE LA SABANA"
FACULTAD = "Facultad de Ingeniería"
MATERIA = "Observabilidad en ambientes productivos"
TITULO = "Laboratorio: pipeline OpenTelemetry end-to-end con Jaeger y Prometheus en GCP y AWS"
ENTREGABLE = "Reporte técnico del laboratorio"
FECHA = "Octubre 2026"
ESTUDIANTES = [
    ("David Aníbal", "Vásquez"),
    ("Sergio Andrés", "Cobos"),
    ("Sebastián", "Bedoya Flórez"),
]

# Paleta tomada del documento de referencia.
ACCENT = "#2E86DE"
NAVY = "#0A2C52"
HEADING = "#0F4761"


def font_faces() -> str:
    faces = [
        ("Aptos", "Aptos.ttf", 400, "normal"),
        ("Aptos", "Aptos-Bold.ttf", 700, "normal"),
        ("Aptos", "Aptos-Italic.ttf", 400, "italic"),
        ("Aptos", "Aptos-Bold-Italic.ttf", 700, "italic"),
        ("Aptos", "Aptos-SemiBold.ttf", 600, "normal"),
        ("Aptos Light", "Aptos-Light.ttf", 400, "normal"),
        ("ArialRef", "arial.ttf", 400, "normal"),
        ("ArialRef", "arialbd.ttf", 700, "normal"),
        ("ArialRef", "ariali.ttf", 400, "italic"),
    ]
    css = []
    for family, file, weight, style in faces:
        path = OFFICE_FONTS / file
        if path.exists():
            css.append(
                f'@font-face {{ font-family: "{family}"; src: url("{path.as_uri()}"); '
                f"font-weight: {weight}; font-style: {style}; }}"
            )
    return "\n".join(css)


CSS = f"""
@page {{ size: A4; margin: 25mm 25mm 22mm 25mm; }}
body {{ font-family: "Aptos", "Helvetica Neue", Arial, sans-serif; font-size: 11pt; line-height: 1.38;
       color: #0d0d0d; }}
/* ---------- Portada ---------- */
.cover {{ height: 247mm; break-after: page; text-align: center; }}
.cover .inst {{ font-size: 10pt; margin: 0 0 9pt; padding-top: 12mm; }}
.cover .inst p {{ margin: 0 0 9pt; }}
.cover h1 {{ font-family: "Aptos Light", "Aptos", sans-serif; font-weight: 400; font-size: 25pt;
            line-height: 1.32; color: #0d0d0d; margin: 18mm 6mm 0; border: none; }}
.cover .rule {{ border-top: 1.5px solid {ACCENT}; margin: 12mm 0 0; }}
.cover .boxes {{ display: flex; margin: 21mm 1mm 0; border: 1px solid {NAVY}; }}
.cover .boxes div {{ flex: 1; padding: 9pt 10pt 12pt; font-size: 10pt; }}
.cover .boxes .m {{ background: #D6E8F7; border-right: 1px solid {NAVY}; }}
.cover .boxes .e {{ background: #EDE9F8; }}
.cover .boxes h4 {{ font-weight: 400; font-size: 10pt; margin: 0 0 8pt; text-transform: uppercase; }}
.cover .boxes p {{ margin: 0 0 6pt; }}
.cover table.est {{ margin: 8mm 1mm 0; width: calc(100% - 2mm); border-collapse: collapse;
                   font-family: "ArialRef", Arial, sans-serif; }}
.cover table.est th {{ background: {NAVY}; color: #fff; font-weight: 400; font-size: 9pt; padding: 9pt;
                      border: none; text-align: center; }}
.cover table.est td {{ border: none; border-bottom: 1px solid #D6E8F7; padding: 6pt 10pt; font-size: 9.5pt;
                      background: #F2F4F7; color: #4a4a4a; text-align: left; }}
.cover table.est td.n {{ background: {ACCENT}; color: #fff; width: 18pt; text-align: center; font-weight: 700;
                        font-size: 8.5pt; }}
.cover table.est b {{ color: {NAVY}; }}
/* ---------- Cuerpo ---------- */
h2 {{ font-family: "Aptos", sans-serif; font-weight: 400; font-size: 16pt; color: {HEADING};
      margin: 20pt 0 8pt; break-after: avoid; }}
h3 {{ font-family: "Aptos", sans-serif; font-weight: 400; font-size: 13pt; color: {HEADING};
      margin: 14pt 0 6pt; break-after: avoid; }}
p {{ margin: 0 0 8pt; }}
li {{ margin-bottom: 4pt; }}
code {{ font-family: Menlo, Consolas, monospace; font-size: 8.8pt; }}
pre {{ font-family: Menlo, Consolas, monospace; font-size: 8pt; background: #F2F4F7; padding: 8pt 10pt;
       white-space: pre-wrap; border: 1px solid #d9dde3; text-align: left; break-inside: avoid; }}
/* Tablas y figuras estilo APA */
p.tnum {{ font-family: "ArialRef", Arial, sans-serif; font-weight: 700; font-size: 8.5pt; margin: 14pt 0 3pt;
         break-after: avoid; }}
p.ttit {{ font-family: "ArialRef", Arial, sans-serif; font-size: 8.5pt; margin: 0 0 4pt; break-after: avoid; }}
p.ftit {{ font-family: "ArialRef", Arial, sans-serif; font-size: 8.5pt; font-style: italic; margin: 0 0 6pt;
         break-after: avoid; }}
p.nota {{ font-family: "ArialRef", Arial, sans-serif; font-size: 8pt; color: #333; margin: 4pt 0 12pt; }}
table {{ border-collapse: collapse; width: 100%; margin: 0 0 12pt; font-family: "ArialRef", Arial, sans-serif;
         font-size: 8.3pt; line-height: 1.25; }}
th, td {{ border: 0.6pt solid #000; padding: 2.5pt 4pt; vertical-align: top; text-align: left; }}
th {{ color: #0B2545; font-weight: 700; }}
tr {{ break-inside: avoid; }}
table code {{ font-size: 7.6pt; }}
figure {{ margin: 0 0 6pt; break-inside: avoid; }}
figure img {{ max-width: 100%; max-height: 120mm; display: block; margin: 0 auto; border: 0.5pt solid #bbb; }}
.mermaid {{ text-align: center; margin: 4pt 0; break-inside: avoid; }}
.mermaid svg {{ max-width: 100%; max-height: 120mm; }}
.mermaid p, .mermaid span, .mermaid div {{ text-align: center !important; }}
.refs p {{ margin-bottom: 7pt; font-size: 10.5pt; word-break: break-word; }}
.pagebreak {{ break-before: page; }}
p.nota code {{ font-size: 7.4pt; }}
"""


def cover() -> str:
    filas = "".join(
        f'<tr><td class="n">{i}</td><td>{nombres} <b>{apellidos}</b></td></tr>'
        for i, (nombres, apellidos) in enumerate(ESTUDIANTES, 1)
    )
    titulo_est = "Estudiante" if len(ESTUDIANTES) == 1 else "Estudiantes"
    return f"""
<section class="cover">
  <div class="inst"><p>{UNIVERSIDAD}</p><p>{FACULTAD}</p><p>{MATERIA}</p></div>
  <h1>{TITULO}</h1>
  <div class="rule"></div>
  <div class="boxes">
    <div class="m"><h4>Materia</h4><p>{MATERIA}</p></div>
    <div class="e"><h4>Entregable</h4><p>{ENTREGABLE}</p><p>{FECHA}</p></div>
  </div>
  <table class="est"><tr><th colspan="2">{titulo_est}</th></tr>{filas}</table>
</section>"""


def build_html() -> None:
    body = markdown.markdown(SRC.read_text(encoding="utf-8"), extensions=["tables", "fenced_code", "sane_lists", "md_in_html"])
    # Bloques ```mermaid -> <div class="mermaid"> para que mermaid.js los renderice.
    body = re.sub(
        r'<pre><code class="language-mermaid">(.*?)</code></pre>',
        lambda m: '<div class="mermaid">' + m.group(1) + "</div>",
        body,
        flags=re.S,
    )
    # En celdas angostas "service-a" se partía por el guion: se mantiene en una sola línea.
    body = re.sub(r"(<td>[^<]*?)(service-[ab])", r'\1<span style="white-space:nowrap">\2</span>', body)
    HTML.write_text(
        f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>{TITULO}</title>
<style>{font_faces()}\n{CSS}</style>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<script>mermaid.initialize({{ startOnLoad: true, theme: "neutral",
  themeVariables: {{ fontFamily: "Aptos, Arial, sans-serif", fontSize: "13px" }} }});</script>
</head><body>{cover()}{body}</body></html>""",
        encoding="utf-8",
    )


def build_pdf() -> None:
    subprocess.run(
        [
            CHROME,
            "--headless=new",
            "--disable-gpu",
            "--no-pdf-header-footer",
            "--allow-file-access-from-files",
            "--virtual-time-budget=20000",
            f"--print-to-pdf={PDF}",
            HTML.as_uri(),
        ],
        check=True,
        capture_output=True,
    )


if __name__ == "__main__":
    build_html()
    build_pdf()
    HTML.unlink()  # el HTML es solo un paso intermedio
    print(f"PDF generado: {PDF}")
