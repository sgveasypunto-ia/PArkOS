/**
 * `csv.ts` — unit tests (HU-F17.4, T4).
 *
 * Covers RFC 4180 quoting/escaping and the UTF-8 BOM prefix. The
 * DOM-touching `downloadCsv`/`exportToCsv` trigger is intentionally NOT
 * exercised here (jsdom has no `URL.createObjectURL`) — see `csv.ts`'s
 * module docstring.
 */
import { describe, expect, it } from 'vitest';

import { CSV_BOM, buildCsv, buildCsvWithBom, escapeCsvField, sanitizeCsvCell } from './csv';

interface Row {
  nombre: string;
  monto: number;
  nota: string | null;
}

describe('escapeCsvField', () => {
  it('T1: a plain field is left unquoted', () => {
    expect(escapeCsvField('efectivo')).toBe('efectivo');
  });

  it('T2: a field containing a comma is quoted', () => {
    expect(escapeCsvField('Bogotá, Colombia')).toBe('"Bogotá, Colombia"');
  });

  it('T3: a field containing a double quote is quoted and the quote is doubled', () => {
    expect(escapeCsvField('dijo "hola"')).toBe('"dijo ""hola"""');
  });

  it('T4: a field containing a line break is quoted', () => {
    expect(escapeCsvField('linea1\nlinea2')).toBe('"linea1\nlinea2"');
  });

  it('T5: a field containing CR is quoted', () => {
    expect(escapeCsvField('a\rb')).toBe('"a\rb"');
  });
});

describe('sanitizeCsvCell (CSV/formula-injection mitigation, OWASP)', () => {
  it.each([
    ['=HYPERLINK("http://evil.test","x")', "'=HYPERLINK(\"http://evil.test\",\"x\")"],
    ['+1+1', "'+1+1"],
    ['-1+1', "'-1+1"],
    ['@SUM(A1:A2)', "'@SUM(A1:A2)"],
    ['\tHola', "'\tHola"],
  ])('T12: a value starting with a formula-trigger char is quote-prefixed (%s)', (input, expected) => {
    expect(sanitizeCsvCell(input)).toBe(expected);
  });

  it('T13: a plain value is left untouched', () => {
    expect(sanitizeCsvCell('ABC123')).toBe('ABC123');
  });

  it('T14: a formula-trigger char is only dangerous as the FIRST character', () => {
    expect(sanitizeCsvCell('Total = 5')).toBe('Total = 5');
  });

  it('T15: buildCsv sanitizes an operator-authored free-text cell before quoting', () => {
    const rows: Row[] = [
      { nombre: 'ok', monto: 1, nota: '=HYPERLINK("http://evil.test","click")' },
    ];
    const csv = buildCsv(
      [
        { header: 'Nombre', accessor: (r: Row) => r.nombre },
        { header: 'Monto', accessor: (r: Row) => r.monto },
        { header: 'Nota', accessor: (r: Row) => r.nota },
      ],
      rows,
    );
    expect(csv).toContain('"\'=HYPERLINK(""http://evil.test"",""click"")"');
    expect(csv).not.toMatch(/,=HYPERLINK/);
  });
});

describe('buildCsv', () => {
  const columns = [
    { header: 'Nombre', accessor: (r: Row) => r.nombre },
    { header: 'Monto', accessor: (r: Row) => r.monto },
    { header: 'Nota', accessor: (r: Row) => r.nota },
  ];

  it('T6: header row uses the Spanish headers verbatim (BR2)', () => {
    const csv = buildCsv(columns, []);
    expect(csv).toBe('Nombre,Monto,Nota');
  });

  it('T7: rows are CRLF-joined (RFC 4180 line terminator)', () => {
    const rows: Row[] = [
      { nombre: 'Juan', monto: 1000, nota: null },
      { nombre: 'Ana', monto: 2000, nota: 'ok' },
    ];
    const csv = buildCsv(columns, rows);
    expect(csv.split('\r\n')).toEqual([
      'Nombre,Monto,Nota',
      'Juan,1000,',
      'Ana,2000,ok',
    ]);
  });

  it('T8: null/undefined cell values become an empty field, never "null"/"undefined"', () => {
    const rows: Row[] = [{ nombre: 'Sin nota', monto: 0, nota: null }];
    const csv = buildCsv(columns, rows);
    expect(csv).toContain('Sin nota,0,');
    expect(csv).not.toContain('null');
  });

  it('T9: a comma/quote-bearing cell value is quoted mid-row', () => {
    const rows: Row[] = [{ nombre: 'Pérez, S.A.', monto: 500, nota: 'dice "bien"' }];
    const csv = buildCsv(columns, rows);
    expect(csv).toContain('"Pérez, S.A.",500,"dice ""bien"""');
  });
});

describe('buildCsvWithBom', () => {
  it('T10: prefixes the UTF-8 BOM before the header row (BR2, Excel/Windows)', () => {
    const csv = buildCsvWithBom([{ header: 'Col', accessor: (r: { v: string }) => r.v }], [
      { v: 'x' },
    ]);
    expect(csv.startsWith(CSV_BOM)).toBe(true);
    expect(csv).toBe(`${CSV_BOM}Col\r\nx`);
  });

  it('T11: CSV_BOM is exactly one U+FEFF character', () => {
    expect(CSV_BOM).toBe('﻿');
    expect(CSV_BOM).toHaveLength(1);
  });
});
