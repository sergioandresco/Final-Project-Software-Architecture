/*
 * Genera docs/reporte-tecnico.docx a partir de docs/reporte-tecnico.md con el mismo diseño del
 * PDF (portada Universidad de La Sabana, tablas y figuras APA, Aptos/Arial).
 *
 *   npm install docx marked          # una sola vez, en cualquier carpeta incluida en NODE_PATH
 *   node docs/build-docx.cjs
 *
 * La Figura 1 (arquitectura) usa docs/arquitectura.png, el diagrama Mermaid ya renderizado.
 */
const fs = require("fs");
const path = require("path");
const { marked } = require("marked");
const {
  AlignmentType, BorderStyle, Document, HeadingLevel, ImageRun, LevelFormat, Packer, PageBreak,
  Paragraph, ShadingType, Table, TableCell, TableLayoutType, TableRow, TextRun, VerticalAlign, WidthType,
} = require("docx");

const DOCS = __dirname;
const SRC = path.join(DOCS, "reporte-tecnico.md");
const OUT = path.join(DOCS, "reporte-tecnico.docx");

// --- Portada (mismos datos que build-pdf.py) ---------------------------------------------------
const UNIVERSIDAD = "UNIVERSIDAD DE LA SABANA";
const FACULTAD = "Facultad de Ingeniería";
const MATERIA = "Observabilidad en ambientes productivos";
const TITULO = "Laboratorio: pipeline OpenTelemetry end-to-end con Jaeger y Prometheus en GCP y AWS";
const ENTREGABLE = "Reporte técnico del laboratorio";
const FECHA = "Octubre 2026";
const ESTUDIANTES = [
  ["David Aníbal", "Vásquez"],
  ["Sergio Andrés", "Cobos"],
  ["Sebastián", "Bedoya Flórez"],
];

// Paleta del documento de referencia.
const ACCENT = "2E86DE";
const NAVY = "0A2C52";
const HEADING = "0F4761";
const TABLE_HEAD = "0B2545";

// A4 con márgenes de 2.5 cm: ancho útil en DXA (1440 = 1 pulgada).
const PAGE_W = 11906;
const MARGIN = 1418;
const CONTENT_W = PAGE_W - 2 * MARGIN;
// Courier New: disponible en Word (Windows/Mac) y en Google Docs, a diferencia de Consolas.
const MONO = "Courier New";

// ------------------------------------------------------------------------------------------------
const decode = (s) =>
  s.replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'");

/** Tokens inline de marked -> TextRun[] conservando negrita, cursiva y código. */
function inlineRuns(tokens, fmt = {}) {
  const runs = [];
  for (const t of tokens || []) {
    switch (t.type) {
      case "strong":
        runs.push(...inlineRuns(t.tokens, { ...fmt, bold: true }));
        break;
      case "em":
        runs.push(...inlineRuns(t.tokens, { ...fmt, italics: true }));
        break;
      case "codespan":
        runs.push(new TextRun({ ...fmt, text: decode(t.text), font: MONO, size: fmt.codeSize || 19 }));
        break;
      case "link":
        runs.push(...inlineRuns(t.tokens, fmt));
        break;
      case "br":
        runs.push(new TextRun({ break: 1 }));
        break;
      case "html":
        break; // spans auxiliares del PDF; en Word no aplican
      default:
        if (t.tokens) runs.push(...inlineRuns(t.tokens, fmt));
        else runs.push(new TextRun({ ...fmt, text: decode(t.text ?? t.raw ?? "") }));
    }
  }
  return runs;
}

/** HTML inline sencillo (<i>, <b>, <code>) de los párrafos con clase -> TextRun[]. */
function htmlRuns(html, fmt = {}) {
  const runs = [];
  const st = { i: false, b: false, code: false };
  for (const m of html.matchAll(/<(\/?)(i|b|code)>|([^<]+)/g)) {
    if (m[2]) st[m[2]] = m[1] !== "/";
    else if (m[3])
      runs.push(new TextRun({
        ...fmt,
        text: decode(m[3]),
        // Solo se fija cuando es verdadero: un `false` explícito anularía la negrita/cursiva del estilo.
        ...(fmt.italics || st.i ? { italics: true } : {}),
        ...(fmt.bold || st.b ? { bold: true } : {}),
        ...(st.code ? { font: MONO, size: (fmt.size || 16) - 1 } : {}),
      }));
  }
  return runs;
}

function pngSize(file) {
  const b = fs.readFileSync(file);
  return { w: b.readUInt32BE(16), h: b.readUInt32BE(20), data: b };
}

function imageParagraph(file, maxW = 600, maxH = 450) {
  const { w, h, data } = pngSize(file);
  const scale = Math.min(maxW / w, maxH / h, 1);
  return new Paragraph({
    alignment: AlignmentType.CENTER,
    keepNext: true,
    spacing: { after: 80 },
    children: [new ImageRun({ type: "png", data, transformation: { width: Math.round(w * scale), height: Math.round(h * scale) } })],
  });
}

const thin = { style: BorderStyle.SINGLE, size: 4, color: "000000" };
const allThin = { top: thin, bottom: thin, left: thin, right: thin };

function apaTable(token) {
  const header = token.header;
  const rows = token.rows;
  // Ancho de columnas: cada una recibe al menos el ancho de su palabra más larga (para no partir
  // "service-a" o "0.63%"), y el resto se reparte en proporción a la longitud del texto.
  const text = (cell) => cell.text.replace(/[`*]/g, "");
  const cols = header.map((h, i) => [h, ...rows.map((r) => r[i])].map(text));
  const CHAR = 95; // DXA aproximados por carácter en Arial 8 pt
  const minW = cols.map((c) => Math.max(...c.flatMap((t) => t.split(/\s+/)).map((w) => w.length)) * CHAR + 200);
  const weights = cols.map((c) => Math.min(Math.max(...c.map((t) => t.length), 6), 55));
  const spare = Math.max(CONTENT_W - minW.reduce((a, b) => a + b, 0), 0);
  const total = weights.reduce((a, b) => a + b, 0);
  let widths = minW.map((m, i) => m + (weights[i] / total) * spare);
  const scale = CONTENT_W / widths.reduce((a, b) => a + b, 0);
  widths = widths.map((w) => Math.floor(w * scale));
  widths[widths.length - 1] += CONTENT_W - widths.reduce((a, b) => a + b, 0);

  const cell = (c, i, isHead) =>
    new TableCell({
      width: { size: widths[i], type: WidthType.DXA },
      borders: allThin,
      margins: { top: 40, bottom: 40, left: 80, right: 80 },
      children: [new Paragraph({
        spacing: { after: 0, line: 240 },
        children: inlineRuns(c.tokens, {
          font: "Arial", size: 16, codeSize: 15,
          ...(isHead ? { bold: true, color: TABLE_HEAD } : {}),
        }),
      })],
    });

  return new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: widths,
    layout: TableLayoutType.FIXED,
    rows: [
      new TableRow({ tableHeader: true, cantSplit: true, children: header.map((c, i) => cell(c, i, true)) }),
      ...rows.map((r) => new TableRow({ cantSplit: true, children: r.map((c, i) => cell(c, i, false)) })),
    ],
  });
}

const CLASS_STYLE = { tnum: "TablaNum", ttit: "TablaTit", ftit: "FigTit", nota: "Nota" };

function classedParagraphs(html) {
  const out = [];
  for (const m of html.matchAll(/<p class="(\w+)">(.*?)<\/p>/gs)) {
    const style = CLASS_STYLE[m[1]];
    out.push(new Paragraph({ style, children: htmlRuns(m[2].replace(/\s*\n\s*/g, " "), { font: "Arial", size: m[1] === "nota" ? 16 : 17 }) }));
  }
  return out;
}

function codeBlock(text) {
  return text.split("\n").map((line, i, all) =>
    new Paragraph({
      style: "Codigo",
      spacing: { after: i === all.length - 1 ? 200 : 0, line: 240 },
      children: [new TextRun({ text: line || " ", font: MONO, size: 16 })],
    }));
}

function figure(html) {
  const out = classedParagraphs(html.replace(/<p class="nota">.*?<\/p>/s, ""));
  const img = html.match(/<img src="([^"]+)"/);
  if (img) out.push(imageParagraph(path.resolve(DOCS, img[1])));
  const pre = html.match(/<pre>([\s\S]*?)<\/pre>/);
  if (pre) out.push(...codeBlock(decode(pre[1])));
  const nota = html.match(/<p class="nota">(.*?)<\/p>/s);
  if (nota) out.push(...classedParagraphs(nota[0]));
  return out;
}

// --- Portada ------------------------------------------------------------------------------------
function cover() {
  const center = (text, opts = {}) =>
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 180 }, ...opts.p, children: [new TextRun({ text, size: 20, ...opts.r })] });
  const navyBorder = { style: BorderStyle.SINGLE, size: 6, color: NAVY };
  const box = (fill, title, lines) =>
    new TableCell({
      width: { size: CONTENT_W / 2, type: WidthType.DXA },
      shading: { type: ShadingType.CLEAR, color: "auto", fill },
      borders: { top: navyBorder, bottom: navyBorder, left: navyBorder, right: navyBorder },
      margins: { top: 180, bottom: 240, left: 160, right: 160 },
      children: [center(title.toUpperCase(), { p: { spacing: { after: 160 } } }), ...lines.map((l) => center(l, { p: { spacing: { after: 100 } } }))],
    });
  const none = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
  const lineBottom = { style: BorderStyle.SINGLE, size: 6, color: "D6E8F7" };
  const NUM_W = 620;

  return [
    center(UNIVERSIDAD, { p: { spacing: { before: 700, after: 180 } } }),
    center(FACULTAD),
    center(MATERIA),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 900, line: 380 },
      children: [new TextRun({ text: TITULO, font: "Aptos Light", size: 50 })],
    }),
    new Paragraph({ spacing: { before: 500, after: 1100 }, border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: ACCENT, space: 1 } }, children: [] }),
    new Table({
      width: { size: CONTENT_W, type: WidthType.DXA },
      columnWidths: [CONTENT_W / 2, CONTENT_W / 2],
      rows: [new TableRow({ children: [box("D6E8F7", "Materia", [MATERIA]), box("EDE9F8", "Entregable", [ENTREGABLE, FECHA])] })],
    }),
    new Paragraph({ spacing: { after: 400 }, children: [] }),
    new Table({
      width: { size: CONTENT_W, type: WidthType.DXA },
      columnWidths: [NUM_W, CONTENT_W - NUM_W],
      rows: [
        new TableRow({
          children: [new TableCell({
            columnSpan: 2,
            width: { size: CONTENT_W, type: WidthType.DXA },
            shading: { type: ShadingType.CLEAR, color: "auto", fill: NAVY },
            borders: { top: none, bottom: none, left: none, right: none },
            margins: { top: 160, bottom: 160 },
            children: [new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 0 }, children: [new TextRun({ text: ESTUDIANTES.length > 1 ? "Estudiantes" : "Estudiante", font: "Arial", size: 18, color: "FFFFFF" })] })],
          })],
        }),
        ...ESTUDIANTES.map(([nombres, apellidos], i) => new TableRow({
          children: [
            new TableCell({
              width: { size: NUM_W, type: WidthType.DXA },
              verticalAlign: VerticalAlign.CENTER,
              shading: { type: ShadingType.CLEAR, color: "auto", fill: ACCENT },
              borders: { top: none, left: none, right: none, bottom: lineBottom },
              margins: { top: 100, bottom: 100 },
              children: [new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 0 }, children: [new TextRun({ text: String(i + 1), font: "Arial", size: 17, bold: true, color: "FFFFFF" })] })],
            }),
            new TableCell({
              width: { size: CONTENT_W - NUM_W, type: WidthType.DXA },
              verticalAlign: VerticalAlign.CENTER,
              shading: { type: ShadingType.CLEAR, color: "auto", fill: "F2F4F7" },
              borders: { top: none, left: none, right: none, bottom: lineBottom },
              margins: { top: 100, bottom: 100, left: 200 },
              children: [new Paragraph({ spacing: { after: 0 }, children: [
                new TextRun({ text: `${nombres} `, font: "Arial", size: 19, color: "4A4A4A" }),
                new TextRun({ text: apellidos, font: "Arial", size: 19, bold: true, color: NAVY }),
              ] })],
            }),
          ],
        })),
      ],
    }),
    new Paragraph({ children: [new PageBreak()] }),
  ];
}

// --- Cuerpo -------------------------------------------------------------------------------------
function body() {
  const out = [];
  let refs = false;
  for (const t of marked.lexer(fs.readFileSync(SRC, "utf8"))) {
    switch (t.type) {
      case "heading":
        out.push(new Paragraph({ heading: t.depth <= 2 ? HeadingLevel.HEADING_1 : HeadingLevel.HEADING_2, children: inlineRuns(t.tokens) }));
        break;
      case "paragraph":
        out.push(new Paragraph({ style: refs ? "Referencia" : undefined, children: inlineRuns(t.tokens) }));
        break;
      case "list":
        for (const item of t.items)
          out.push(new Paragraph({
            numbering: { reference: t.ordered ? "numerada" : "vinetas", level: 0 },
            spacing: { after: 80 },
            children: inlineRuns(item.tokens.flatMap((x) => x.tokens || [x])),
          }));
        break;
      case "table":
        out.push(apaTable(t), new Paragraph({ spacing: { after: 120 }, children: [] }));
        break;
      case "code":
        if (t.lang === "mermaid") out.push(imageParagraph(path.join(DOCS, "arquitectura.png"), 560, 520));
        else out.push(...codeBlock(t.text));
        break;
      case "html": {
        const h = t.raw.trim();
        if (h.includes('class="pagebreak"')) out.push(new Paragraph({ children: [new PageBreak()] }));
        else if (h.startsWith('<div class="refs"')) refs = true;
        else if (h.startsWith("</div>")) refs = false;
        else if (h.startsWith("<figure>")) out.push(...figure(h));
        else out.push(...classedParagraphs(h));
        break;
      }
      default:
        break;
    }
  }
  return out;
}

// --- Documento ----------------------------------------------------------------------------------
const doc = new Document({
  creator: ESTUDIANTES.map(([n, a]) => `${n} ${a}`).join(", "),
  title: TITULO,
  styles: {
    default: { document: { run: { font: "Aptos", size: 22 }, paragraph: { spacing: { after: 160, line: 276 } } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: "Aptos", size: 32, color: HEADING },
        paragraph: { spacing: { before: 400, after: 160 }, keepNext: true, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: "Aptos", size: 26, color: HEADING },
        paragraph: { spacing: { before: 280, after: 120 }, keepNext: true, outlineLevel: 1 } },
      { id: "TablaNum", name: "Tabla número", basedOn: "Normal", run: { font: "Arial", size: 17, bold: true },
        paragraph: { spacing: { before: 240, after: 40 }, keepNext: true } },
      { id: "TablaTit", name: "Tabla título", basedOn: "Normal", run: { font: "Arial", size: 17 },
        paragraph: { spacing: { after: 80 }, keepNext: true } },
      { id: "FigTit", name: "Figura título", basedOn: "Normal", run: { font: "Arial", size: 17, italics: true },
        paragraph: { spacing: { after: 120 }, keepNext: true } },
      { id: "Nota", name: "Nota", basedOn: "Normal", run: { font: "Arial", size: 16, color: "333333" },
        paragraph: { spacing: { before: 60, after: 240 } } },
      { id: "Referencia", name: "Referencia", basedOn: "Normal", run: { size: 21 },
        paragraph: { spacing: { after: 140 } } },
      { id: "Codigo", name: "Código", basedOn: "Normal", run: { font: MONO, size: 16 },
        paragraph: { shading: { type: ShadingType.CLEAR, color: "auto", fill: "F2F4F7" } } },
    ],
  },
  numbering: {
    config: [
      { reference: "numerada", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 360, hanging: 360 } } } }] },
      { reference: "vinetas", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 360, hanging: 360 } } } }] },
    ],
  },
  sections: [{
    properties: { page: { size: { width: PAGE_W, height: 16838 }, margin: { top: MARGIN, bottom: 1247, left: MARGIN, right: MARGIN } } },
    children: [...cover(), ...body()],
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(OUT, buf);
  console.log(`DOCX generado: ${OUT}`);
});
