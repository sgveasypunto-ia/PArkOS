/**
 * `csv.ts` — RFC 4180 CSV export helper (HU-F17.4, T3).
 *
 * Shared by every reportería `DataTable`'s "Exportar CSV" button
 * (`Reporteria.tsx`, `ReporteriaFinanciera.tsx`,
 * `ReporteriaSuscripciones.tsx`): BR2 requires Spanish column headers,
 * UTF-8 **with BOM** (Excel on Windows mojibakes accented characters —
 * "Número", "Días restantes" — without it), and RFC 4180 quoting/escaping.
 * BR2 also requires the export to respect the table's ACTIVE filters —
 * this module takes already-filtered rows as input and never fetches or
 * widens the dataset itself, so that guarantee lives at the call site
 * (each page passes its current SWR-filtered `data`/`items`, never an
 * unfiltered "export everything" source).
 *
 * No existing CSV helper was found in the repo (`grep -i csv` across
 * `apps/`/`backend/` before writing this — only `plan.md` and an
 * unrelated PowerShell module matched), so this is new, not a
 * duplicate.
 *
 * Split into a pure, fully unit-testable content builder (`buildCsv`)
 * and a thin DOM-touching trigger (`downloadCsv`/`exportToCsv`) — jsdom
 * does not implement `URL.createObjectURL`, so the download side is
 * exercised manually in the browser rather than under vitest; the
 * quoting/escaping/BOM logic that actually matters for RFC 4180
 * correctness is the part under test.
 *
 * CSV/formula injection (OWASP): several exported columns carry
 * operator-authored free text (e.g. ``ingreso.observaciones``, a
 * nullable ``Text`` column any operador can set at vehicle entry — no
 * format constraint). If a field's value starts with ``=``, ``+``,
 * ``-``, ``@``, a tab, or a CR, Excel/Sheets treats it as a formula the
 * moment an admin opens the exported file, not as data — a stored
 * payload (e.g. a ``HYPERLINK``/``WEBSERVICE`` call) planted in that
 * field now runs in the spreadsheet app that opens it. `sanitizeCsvCell`
 * applies the standard mitigation (prefix with a literal `'` so the
 * leading character can never again be the first character of the
 * cell) BEFORE RFC 4180 quoting, for every cell.
 */

export interface CsvColumn<T> {
  /** Column header, already in Spanish (BR2) — written as-is, no i18n lookup here. */
  header: string;
  /** Extracts this column's raw value for one row. `null`/`undefined` become `''`. */
  accessor: (row: T) => string | number | null | undefined;
}

const CRLF = '\r\n';
/** UTF-8 BOM — forces Excel on Windows to read the file as UTF-8 (BR2). */
export const CSV_BOM = '﻿';

/**
 * RFC 4180 §2.5/2.6/2.7: a field is quoted only when it contains the
 * delimiter, a quote, or a line break; an embedded quote is doubled.
 * Fields that need no quoting are left bare (smaller files, and matches
 * every real-world RFC 4180 writer/reader).
 */
export function escapeCsvField(value: string): string {
  const needsQuoting = /[",\r\n]/.test(value);
  const escaped = value.replace(/"/g, '""');
  return needsQuoting ? `"${escaped}"` : escaped;
}

function cellToString(raw: string | number | null | undefined): string {
  return raw === null || raw === undefined ? '' : String(raw);
}

/** Leading characters that make Excel/Sheets interpret a cell as a formula. */
const FORMULA_TRIGGER_CHARS = /^[=+\-@\t\r]/;

/**
 * CSV/formula-injection mitigation (OWASP): prefixes the value with a
 * literal `'` when it starts with a formula-trigger character, so the
 * cell can never be parsed as a formula by the spreadsheet app that
 * opens the export. Applied to every cell, not just known-risky
 * columns — safe values are untouched, this is a pure identity
 * transform for them.
 */
export function sanitizeCsvCell(value: string): string {
  return FORMULA_TRIGGER_CHARS.test(value) ? `'${value}` : value;
}

/**
 * Builds the CSV body (header row + data rows, CRLF-joined, NO BOM) —
 * the pure, directly unit-testable core. `buildCsvWithBom` below is
 * what the download path actually writes to the file.
 */
export function buildCsv<T>(columns: CsvColumn<T>[], rows: T[]): string {
  const headerLine = columns.map((c) => escapeCsvField(c.header)).join(',');
  const dataLines = rows.map((row) =>
    columns
      .map((c) => escapeCsvField(sanitizeCsvCell(cellToString(c.accessor(row)))))
      .join(','),
  );
  return [headerLine, ...dataLines].join(CRLF);
}

/** `buildCsv` output prefixed with the UTF-8 BOM (BR2, Excel/Windows). */
export function buildCsvWithBom<T>(columns: CsvColumn<T>[], rows: T[]): string {
  return CSV_BOM + buildCsv(columns, rows);
}

/** Triggers a browser download of `content` as `filename` (DOM side effect, not unit-tested). */
export function downloadCsv(filename: string, content: string): void {
  const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

/** Builds the BOM-prefixed CSV for `rows` and triggers the browser download. */
export function exportToCsv<T>(filename: string, columns: CsvColumn<T>[], rows: T[]): void {
  downloadCsv(filename, buildCsvWithBom(columns, rows));
}
