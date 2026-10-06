/**
 * `resumenCierrePdf.ts` — PDF export of the read-only post-close turn
 * summary (PT-5, "Descargar PDF").
 *
 * Presentation-only: the caller (`<ResumenCierreTurno>`) hands over
 * already-formatted label/value rows grouped in sections, so this module
 * knows nothing about COP, dates or the backend contract. jsPDF is loaded
 * lazily (dynamic import) so it never weighs on the renderer's first paint.
 *
 * jsPDF's built-in Helvetica covers Latin-1 (accents, ñ); text is passed
 * through `toLatin1` so a stray glyph outside that range (em dash, curly
 * quotes) degrades to ASCII instead of printing garbage.
 */

export interface ResumenCierrePdfRow {
  label: string;
  value: string;
}

export interface ResumenCierrePdfSection {
  heading: string;
  rows: ResumenCierrePdfRow[];
}

export interface ResumenCierrePdfData {
  title: string;
  subtitle?: string;
  sections: ResumenCierrePdfSection[];
  /** Footer note (e.g. generation timestamp). */
  footer?: string;
  /** Without extension. */
  fileName: string;
}

const REPLACEMENTS: Record<string, string> = {
  '—': '-',
  '–': '-',
  '‘': "'",
  '’': "'",
  '“': '"',
  '”': '"',
  '…': '...',
};

/** Keep Latin-1, map the common typographic glyphs, drop the rest. */
export function toLatin1(text: string): string {
  let out = '';
  for (const ch of text) {
    const code = ch.charCodeAt(0);
    const mapped = REPLACEMENTS[ch];
    if (mapped !== undefined) {
      out += mapped;
    } else if (ch === '\n' || ch === '\t') {
      out += ' ';
    } else if ((code >= 0x20 && code <= 0x7e) || (code >= 0xa0 && code <= 0xff)) {
      // Printable ASCII + Latin-1 supplement; C0/C1 controls (0x80-0x9f) are not.
      out += ch;
    } else {
      out += '?';
    }
  }
  return out;
}

const MARGIN = 18;
const LINE = 6.5;

export async function descargarResumenCierrePdf(data: ResumenCierrePdfData): Promise<void> {
  const { jsPDF } = await import('jspdf');
  const doc = new jsPDF({ unit: 'mm', format: 'a4' });
  const pageHeight = doc.internal.pageSize.getHeight();
  const pageWidth = doc.internal.pageSize.getWidth();
  let y = MARGIN;

  const ensureSpace = (needed: number): void => {
    if (y + needed > pageHeight - MARGIN) {
      doc.addPage();
      y = MARGIN;
    }
  };

  doc.setFont('helvetica', 'bold');
  doc.setFontSize(16);
  doc.text(toLatin1(data.title), MARGIN, y);
  y += LINE + 1;

  if (data.subtitle) {
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(10);
    doc.text(toLatin1(data.subtitle), MARGIN, y);
    y += LINE;
  }
  y += 2;

  for (const section of data.sections) {
    ensureSpace(LINE * 2);
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(11);
    doc.text(toLatin1(section.heading), MARGIN, y);
    y += 2;
    doc.setDrawColor(180);
    doc.line(MARGIN, y, pageWidth - MARGIN, y);
    y += LINE - 1;

    doc.setFont('helvetica', 'normal');
    doc.setFontSize(10);
    for (const row of section.rows) {
      const valueLines = doc.splitTextToSize(
        toLatin1(row.value),
        pageWidth - MARGIN * 2 - 70,
      ) as string[];
      ensureSpace(LINE * Math.max(1, valueLines.length));
      doc.text(toLatin1(row.label), MARGIN, y);
      doc.text(valueLines, pageWidth - MARGIN, y, { align: 'right' });
      y += LINE * Math.max(1, valueLines.length);
    }
    y += 3;
  }

  if (data.footer) {
    ensureSpace(LINE);
    doc.setFont('helvetica', 'italic');
    doc.setFontSize(8);
    doc.text(toLatin1(data.footer), MARGIN, y);
  }

  doc.save(`${data.fileName}.pdf`);
}
