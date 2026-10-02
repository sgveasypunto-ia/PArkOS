/**
 * `pdf.ts` — unit tests (HU-F18.4, T3).
 *
 * Covers BR1 (the SHA-256 hash is computed over the exact serialized
 * tabular content, deterministically, via the native Web Crypto API) and
 * the "verification" flow an external auditor would run manually:
 * re-serialize the same rows/columns, recompute the hash, and confirm it
 * matches the value embedded in the PDF footer.
 *
 * Mirrors `csv.test.ts`'s split: the pure core (`buildHashableTable`,
 * `computeSha256Hex`, `buildSignedPdf`) is exhaustively tested here. The
 * DOM-touching trigger (`exportSignedPdf`, which calls `doc.save(...)`) is
 * NOT exercised under vitest/jsdom — same reason `csv.ts`'s `downloadCsv`
 * isn't: jsdom has no `URL.createObjectURL`, and jsPDF's browser `save()`
 * goes through the same download-anchor mechanism.
 */
import { describe, expect, it } from 'vitest';

import {
  buildHashableTable,
  buildSignedPdf,
  computeSha256Hex,
} from './pdf';
import type { CsvColumn } from './csv';

interface Row {
  medio: string;
  esperado: number;
  reportado: number;
  diferencia: number | null;
}

const columns: CsvColumn<Row>[] = [
  { header: 'Medio', accessor: (r) => r.medio },
  { header: 'Esperado', accessor: (r) => r.esperado },
  { header: 'Reportado', accessor: (r) => r.reportado },
  { header: 'Diferencia', accessor: (r) => r.diferencia },
];

const rows: Row[] = [
  { medio: 'Efectivo', esperado: 100000, reportado: 99000, diferencia: -1000 },
  { medio: 'Datáfono', esperado: 50000, reportado: 50000, diferencia: 0 },
];

describe('buildHashableTable', () => {
  it('T1: reuses RFC 4180 quoting (comma-bearing header/cell is quoted)', () => {
    const content = buildHashableTable(
      [{ header: 'Nombre, Sucursal', accessor: (r: { v: string }) => r.v }],
      [{ v: 'Bogotá, Colombia' }],
    );
    expect(content).toBe('"Nombre, Sucursal"\r\n"Bogotá, Colombia"');
  });

  it('T2: does NOT apply the anti-formula-injection prefix (unlike buildCsv) — this string is only ever hashed, never opened in a spreadsheet', () => {
    const content = buildHashableTable(
      [{ header: 'Nota', accessor: (r: { nota: string }) => r.nota }],
      [{ nota: '=HYPERLINK("http://evil.test","x")' }],
    );
    expect(content).toBe(
      'Nota\r\n"=HYPERLINK(""http://evil.test"",""x"")"',
    );
  });

  it('T3: null/undefined cells become an empty field, never the literal "null"/"undefined"', () => {
    const content = buildHashableTable(columns, [
      { medio: 'Efectivo', esperado: 1, reportado: 1, diferencia: null },
    ]);
    expect(content.endsWith(',')).toBe(true);
    expect(content).not.toContain('null');
  });

  it('T4: rows are CRLF-joined, no BOM, same as buildCsv', () => {
    const content = buildHashableTable(columns, rows);
    expect(content.startsWith('﻿')).toBe(false);
    expect(content.split('\r\n')).toEqual([
      'Medio,Esperado,Reportado,Diferencia',
      'Efectivo,100000,99000,-1000',
      'Datáfono,50000,50000,0',
    ]);
  });
});

describe('computeSha256Hex', () => {
  it('T5: matches the well-known SHA-256 test vector for the empty string', async () => {
    const hex = await computeSha256Hex('');
    expect(hex).toBe(
      'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    );
  });

  it('T6: matches the well-known SHA-256 test vector for "abc"', async () => {
    const hex = await computeSha256Hex('abc');
    expect(hex).toBe(
      'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad',
    );
  });

  it('T7: is deterministic for the same input', async () => {
    const [a, b] = await Promise.all([
      computeSha256Hex('contenido estable'),
      computeSha256Hex('contenido estable'),
    ]);
    expect(a).toBe(b);
  });

  it('T8: any change in the input changes the hash (tamper detection)', async () => {
    const original = await computeSha256Hex(buildHashableTable(columns, rows));
    const tampered = await computeSha256Hex(
      buildHashableTable(columns, [
        { ...rows[0]!, reportado: rows[0]!.reportado + 1 },
        rows[1]!,
      ]),
    );
    expect(tampered).not.toBe(original);
  });
});

describe('buildSignedPdf (verification flow, BR1)', () => {
  it('T9: the embedded hash matches an independently recomputed hash of the same serialized content (manual-verification flow)', async () => {
    const { hashHex } = await buildSignedPdf(columns, rows, {
      title: 'Arqueo — detalle',
    });
    const recomputed = await computeSha256Hex(buildHashableTable(columns, rows));
    expect(hashHex).toBe(recomputed);
  });

  it('T10: the hash is embedded verbatim in the PDF footer (readable without special tooling)', async () => {
    const { doc, hashHex } = await buildSignedPdf(columns, rows, {
      title: 'Arqueo — detalle',
    });
    const raw = Buffer.from(doc.output('arraybuffer')).toString('latin1');
    expect(raw).toContain(hashHex);
    expect(raw).toContain('SHA-256');
  });

  it('T11: generates successfully with no logo (BR2 — missing logo is not an error)', async () => {
    await expect(
      buildSignedPdf(columns, rows, { title: 'Sin logo' }),
    ).resolves.toBeDefined();
  });

  it('T12: generates successfully with no logo when logoDataUrl is explicitly null', async () => {
    await expect(
      buildSignedPdf(columns, rows, { title: 'Sin logo', logoDataUrl: null }),
    ).resolves.toBeDefined();
  });

  it('T13: embeds a valid logo image header without throwing (BR2)', async () => {
    // 1x1 transparent PNG, the smallest valid PNG payload.
    const tinyPng =
      'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=';
    await expect(
      buildSignedPdf(columns, rows, { title: 'Con logo', logoDataUrl: tinyPng }),
    ).resolves.toBeDefined();
  });

  it('T14: an unsupported/corrupt logo data URL is skipped gracefully, never blocking the export (BR2)', async () => {
    await expect(
      buildSignedPdf(columns, rows, {
        title: 'Logo invalido',
        logoDataUrl: 'data:application/octet-stream;base64,not-an-image',
      }),
    ).resolves.toBeDefined();
  });

  it('T15: handles an empty dataset (header only) without throwing', async () => {
    const { hashHex } = await buildSignedPdf(columns, [], { title: 'Vacio' });
    expect(hashHex).toBe(
      await computeSha256Hex(buildHashableTable(columns, [])),
    );
  });

  it('T16: paginates when the dataset overflows one page, repeating the header and the signed footer on every page', async () => {
    const manyRows: Row[] = Array.from({ length: 80 }, (_, i) => ({
      medio: `Sucursal ${i}`,
      esperado: i,
      reportado: i,
      diferencia: 0,
    }));
    const { doc, hashHex } = await buildSignedPdf(columns, manyRows, {
      title: 'Resumen multi-pagina',
    });
    expect(doc.getNumberOfPages()).toBeGreaterThan(1);
    const raw = Buffer.from(doc.output('arraybuffer')).toString('latin1');
    const occurrences = raw.split(hashHex).length - 1;
    expect(occurrences).toBeGreaterThanOrEqual(doc.getNumberOfPages());
  });
});
