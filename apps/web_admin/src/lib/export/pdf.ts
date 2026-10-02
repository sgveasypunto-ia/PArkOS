/**
 * `pdf.ts` — signed PDF export with an embedded, independently-verifiable
 * SHA-256 hash (HU-F18.4, T1).
 *
 * CU-10 (arqueos) is the only use case that needs "signed" evidence for
 * external auditors. BR1: the hash is computed over the EXACT tabular
 * content exported — never over the final PDF bytes, which would carry
 * variable metadata (generation timestamp, jsPDF internals) that an
 * auditor re-running the hash on the same source data could never
 * reproduce. The algorithm and the hex value are printed in the document
 * itself so the check is a plain "copy the table, hash it, compare" —
 * no tooling beyond a browser console is required.
 *
 * `buildHashableTable` deliberately reuses `csv.ts`'s RFC 4180 quoting
 * (`escapeCsvField`) as the deterministic serialization format (same
 * shape the reportería CSV export already uses, HU-F17.4) but skips its
 * anti-formula-injection prefix (`sanitizeCsvCell`): that mitigation only
 * matters when the string is opened in Excel/Sheets, which never happens
 * here — this string exists solely to be hashed.
 *
 * BR1 also requires the native Web Crypto API (`crypto.subtle.digest`) —
 * no hashing library is added; it ships with every evergreen browser.
 *
 * Split into a pure, fully unit-testable core (`buildHashableTable`,
 * `computeSha256Hex`, `buildSignedPdf`) and a thin DOM-touching trigger
 * (`exportSignedPdf`) — same shape as `csv.ts`'s `buildCsv`/`downloadCsv`
 * split. `buildSignedPdf` only builds the in-memory jsPDF document (no
 * download triggered), so it's exercised directly under vitest; the
 * actual `doc.save(...)` call goes through the same download-anchor
 * mechanism jsdom doesn't implement (see `csv.ts`'s `downloadCsv`
 * docstring), so it isn't unit-tested.
 *
 * No PDF-generation library existed in the repo before this change
 * (checked `apps/web_admin/package.json` and `apps/pnpm-lock.yaml`) — one
 * was added: `jspdf` (100% client-side, no server dependency, the
 * lightest/most mature option for this).
 *
 * Errors: a failure during PDF generation (OOM, an extremely large
 * dataset) is never swallowed here — every function below lets the
 * exception propagate so the caller can show an explicit error instead of
 * silently handing back a corrupt file. The one intentional exception is
 * BR2's logo header: a missing or unembeddable logo is NOT an error (the
 * HU explicitly says so), so that one step is wrapped narrowly and only
 * degrades to "no logo header".
 */
import { jsPDF } from 'jspdf';

import { escapeCsvField, type CsvColumn } from './csv';

const CRLF = '\r\n';

/**
 * BR1: deterministic, dependency-free serialization of the exact
 * tabular content being exported — same column/row order the PDF table
 * renders, RFC 4180-quoted (`escapeCsvField`), CRLF-joined, no BOM.
 * Unlike `buildCsv`, this does NOT apply `sanitizeCsvCell`'s
 * anti-formula-injection prefix: that mitigation exists for spreadsheet
 * apps opening the file, which is irrelevant to a string that is only
 * ever hashed.
 */
export function buildHashableTable<T>(columns: CsvColumn<T>[], rows: T[]): string {
  const headerLine = columns.map((c) => escapeCsvField(c.header)).join(',');
  const dataLines = rows.map((row) =>
    columns
      .map((c) => {
        const raw = c.accessor(row);
        const value = raw === null || raw === undefined ? '' : String(raw);
        return escapeCsvField(value);
      })
      .join(','),
  );
  return [headerLine, ...dataLines].join(CRLF);
}

function toHex(buffer: ArrayBuffer): string {
  return Array.from(new Uint8Array(buffer))
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('');
}

/**
 * BR1: SHA-256 of `content` as a lowercase hex string, via the browser's
 * native Web Crypto API (`crypto.subtle.digest`) — no hashing library.
 */
export async function computeSha256Hex(content: string): Promise<string> {
  const bytes = new TextEncoder().encode(content);
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return toHex(digest);
}

export interface PdfExportOptions {
  /** Document title, printed in the header. */
  title: string;
  /** Optional subtitle (e.g. a date range or branch name), printed under the title. */
  subtitle?: string;
  /**
   * Data URL (`data:image/<png|jpeg|webp>;base64,...`) of the sucursal's
   * logo (`documentos.tipo='logo'`, HU-F15.4), or `null`/`undefined` when
   * none is loaded. BR2: a missing logo is NOT an error — the PDF is
   * generated the same way, just without the logo header.
   */
  logoDataUrl?: string | null;
}

const PAGE_MARGIN_MM = 14;
const FOOTER_HEIGHT_MM = 16;
const ROW_HEIGHT_MM = 7;
const LOGO_SIZE_MM = 14;

/** Maps a `data:image/<ext>;...` URL to the format string jsPDF's `addImage` expects, or `null` when unrecognized. */
function detectImageFormat(dataUrl: string): 'PNG' | 'JPEG' | 'WEBP' | null {
  const match = /^data:image\/(png|jpe?g|webp)/i.exec(dataUrl);
  if (!match) return null;
  const ext = match[1]!.toLowerCase();
  if (ext === 'png') return 'PNG';
  if (ext === 'webp') return 'WEBP';
  return 'JPEG';
}

/**
 * Builds the signed PDF document in memory (no DOM download triggered —
 * see module docstring). Renders one simple table (no `autotable`
 * dependency, per T1's "one library only"): an even column-width grid,
 * paginating when rows overflow the page. BR2's logo header is drawn
 * first when `options.logoDataUrl` resolves to a recognized image
 * format; BR1's hash footer (algorithm + hex value) is drawn on every
 * page, so the evidence is verifiable from any single printed page.
 */
export async function buildSignedPdf<T>(
  columns: CsvColumn<T>[],
  rows: T[],
  options: PdfExportOptions,
): Promise<{ doc: jsPDF; hashHex: string }> {
  const hashableContent = buildHashableTable(columns, rows);
  const hashHex = await computeSha256Hex(hashableContent);

  const doc = new jsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4' });
  const pageWidth = doc.internal.pageSize.getWidth();
  const pageHeight = doc.internal.pageSize.getHeight();
  const usableWidth = pageWidth - PAGE_MARGIN_MM * 2;

  const format = options.logoDataUrl ? detectImageFormat(options.logoDataUrl) : null;
  const hasLogo = format !== null;
  if (options.logoDataUrl && format) {
    try {
      doc.addImage(options.logoDataUrl, format, PAGE_MARGIN_MM, PAGE_MARGIN_MM, LOGO_SIZE_MM, LOGO_SIZE_MM);
    } catch {
      // BR2: an unembeddable logo degrades to "no logo header" — it
      // never blocks the signed export itself.
    }
  }

  const textX = PAGE_MARGIN_MM + (hasLogo ? LOGO_SIZE_MM + 4 : 0);
  doc.setFontSize(14);
  doc.text(options.title, textX, PAGE_MARGIN_MM + 6);
  if (options.subtitle) {
    doc.setFontSize(10);
    doc.text(options.subtitle, textX, PAGE_MARGIN_MM + 12);
  }

  const colWidth = usableWidth / Math.max(columns.length, 1);
  const tableTop = PAGE_MARGIN_MM + Math.max(hasLogo ? LOGO_SIZE_MM : 0, 18) + 6;

  function drawHeaderRow(y: number): number {
    doc.setFontSize(9);
    doc.setFont('helvetica', 'bold');
    columns.forEach((col, i) => {
      doc.text(col.header, PAGE_MARGIN_MM + i * colWidth + 1, y);
    });
    doc.setFont('helvetica', 'normal');
    doc.line(PAGE_MARGIN_MM, y + 2, PAGE_MARGIN_MM + usableWidth, y + 2);
    return y + ROW_HEIGHT_MM;
  }

  /** BR1: algorithm + hex hash, printed verbatim (no wrapping) so an auditor can copy it directly. */
  function drawSignedFooter(): void {
    const footerTop = pageHeight - FOOTER_HEIGHT_MM;
    doc.setFontSize(7);
    doc.setTextColor(90);
    doc.line(PAGE_MARGIN_MM, footerTop, pageWidth - PAGE_MARGIN_MM, footerTop);
    doc.text('Algoritmo: SHA-256', PAGE_MARGIN_MM, footerTop + 5);
    doc.text(`Hash del contenido tabular: ${hashHex}`, PAGE_MARGIN_MM, footerTop + 10);
    doc.setTextColor(0);
  }

  let cursorY = drawHeaderRow(tableTop);

  for (const row of rows) {
    if (cursorY > pageHeight - FOOTER_HEIGHT_MM - ROW_HEIGHT_MM) {
      drawSignedFooter();
      doc.addPage();
      cursorY = drawHeaderRow(PAGE_MARGIN_MM + 6);
    }
    doc.setFontSize(9);
    columns.forEach((col, i) => {
      const raw = col.accessor(row);
      const text = raw === null || raw === undefined ? '' : String(raw);
      doc.text(text, PAGE_MARGIN_MM + i * colWidth + 1, cursorY);
    });
    cursorY += ROW_HEIGHT_MM;
  }

  drawSignedFooter();

  return { doc, hashHex };
}

/**
 * Triggers the browser download of the signed PDF (DOM side effect, not
 * unit-tested — mirrors `csv.ts`'s `downloadCsv`/`exportToCsv`). Returns
 * the embedded hash so the caller can surface it (e.g. a toast) if
 * desired. Errors propagate to the caller — see module docstring's
 * "Errores" note.
 */
export async function exportSignedPdf<T>(
  filename: string,
  columns: CsvColumn<T>[],
  rows: T[],
  options: PdfExportOptions,
): Promise<string> {
  const { doc, hashHex } = await buildSignedPdf(columns, rows, options);
  doc.save(filename);
  return hashHex;
}
