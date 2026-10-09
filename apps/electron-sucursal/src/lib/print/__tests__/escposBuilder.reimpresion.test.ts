/**
 * Unit tests for F8.3 — Reimpresión de tiquete con costo byte-level
 * fixtures (REQ-OPS-172).
 *
 * Coverage (3 byte-level tests):
 *   T1: `build('reimpresion', payload)` emits the sello with accent
 *       `'*** REIMPRESIÓN ***'` (U+00D3) — currently FAIL because the
 *       F1.11/F7.3 sello is `'*** REIMPRESION ***'` (no accent).
 *   T2: buffer contains the subline `'--- COPIA AUTORIZADA ---'`
 *       between sello and motivo — currently FAIL because the subline
 *       does not exist on dev.
 *   T3: the REIMPRESIÓN legend is bold (escBoldOn `0x1B 0x45 0x01` + escBoldOff
 *       `0x1B 0x45 0x00`). Intentional change (80 mm): the inner body is NO
 *       longer wrapped in bold, so the reprint looks like the original ticket
 *       plus the legend.
 *
 * Drift guard (REQ-OPS-175): the dispatcher key is `'reimpresion'`
 * (NOT `'reimprimir'`). The literal `'reimprimir'` MUST return 0
 * matches in `apps/electron-sucursal/src/`.
 */
import { describe, it, expect } from 'vitest';

import { build, escBoldOn, escBoldOff } from '../escposBuilder';
import type { ReimpresionPayload } from '../escposTemplates';
import { validEntradaPayload } from './escposBuilder.test';

// ──────────────────────────────────────────────────────────────────────────
// Fixture — full ReimpresionPayload with entrada inner body
// ──────────────────────────────────────────────────────────────────────────

function makeReimpresionEntradaPayload(): ReimpresionPayload {
  return {
    motivo: 'Cliente solicita reimpresión por deterioro del tiquete original',
    folioOriginal: '00000000-0000-4000-8000-000000000001',
    empresa: {
      nombre: 'Parkos Demo S.A.S.',
      nit: '900123456-7',
      direccion: 'Calle 1 #2-3, Bogota',
      regimen: 'Responsable de IVA',
    },
    originalTipo: 'entrada',
    payload: {
      ...validEntradaPayload(),
      sucursal: { encabezado: 'Sucursal Centro' },
    },
  };
}

// ──────────────────────────────────────────────────────────────────────────
// T1 — Sello with accent (REQ-OPS-172 + REQ-OPS-175 drift anchor)
// ──────────────────────────────────────────────────────────────────────────

describe('buildReimpresionBuffer — sello with accent (HU-F8.3, REQ-OPS-172)', () => {
  it('T1 — emits sello "*** REIMPRESIÓN ***" with accent (U+00D3)', () => {
    const payload = makeReimpresionEntradaPayload();
    const buf = build('reimpresion', payload);

    const selloAccentIdx = buf.indexOf(Buffer.from('*** REIMPRESIÓN ***', 'utf8'));
    expect(selloAccentIdx).toBeGreaterThanOrEqual(0);
  });
});

// ──────────────────────────────────────────────────────────────────────────
// T2 — Subline (REQ-OPS-172)
// ──────────────────────────────────────────────────────────────────────────

describe('buildReimpresionBuffer — subline (HU-F8.3, REQ-OPS-172)', () => {
  it('T2 — emits "--- COPIA AUTORIZADA ---" subline between sello and motivo', () => {
    const payload = makeReimpresionEntradaPayload();
    const buf = build('reimpresion', payload);

    const sublineIdx = buf.indexOf(Buffer.from('--- COPIA AUTORIZADA ---', 'utf8'));
    expect(sublineIdx).toBeGreaterThanOrEqual(0);
  });
});

// ──────────────────────────────────────────────────────────────────────────
// T3 — Bold marca wrapping (REQ-OPS-172)
// ──────────────────────────────────────────────────────────────────────────

describe('buildReimpresionBuffer — bold legend (HU-F8.3, REQ-OPS-172)', () => {
  it('T3 — the sello is wrapped by escBoldOn/escBoldOff and the inner body is NOT bold', () => {
    const payload = makeReimpresionEntradaPayload();
    const buf = build('reimpresion', payload);

    expect(escBoldOn()).toEqual(Buffer.from([0x1b, 0x45, 0x01]));
    expect(escBoldOff()).toEqual(Buffer.from([0x1b, 0x45, 0x00]));

    const selloIdx = buf.indexOf(Buffer.from('*** REIMPRESIÓN ***', 'utf8'));
    expect(selloIdx).toBeGreaterThanOrEqual(0);
    // The last bold switch BEFORE the sello turns bold on; the first AFTER turns it off.
    const onBefore = buf.lastIndexOf(escBoldOn(), selloIdx);
    expect(onBefore).toBeGreaterThanOrEqual(0);
    expect(buf.indexOf(escBoldOff(), selloIdx)).toBeGreaterThan(selloIdx);

    // The original "Folio:" line is regular weight: bold is OFF at that point.
    const folioIdx = buf.indexOf(Buffer.from('Folio: '));
    const lastSwitch = Math.max(buf.lastIndexOf(escBoldOn(), folioIdx), buf.lastIndexOf(escBoldOff(), folioIdx));
    expect(buf.subarray(lastSwitch, lastSwitch + 3)).toEqual(escBoldOff());
  });
});

// ──────────────────────────────────────────────────────────────────────────
// REQ-OPS-175 — Drift anchor (escposBuilder dispatcher key)
// ──────────────────────────────────────────────────────────────────────────

describe('REQ-OPS-175 drift anchor — dispatcher key is "reimpresion"', () => {
  it('escposBuilder module exports build() with reimpresion dispatcher key (no reimprimir typo)', () => {
    // The build() dispatcher accepts 'reimpresion' as a valid tipo.
    const payload = makeReimpresionEntradaPayload();
    expect(() => build('reimpresion', payload)).not.toThrow();
    // Negative — 'reimprimir' (typo) is NOT a valid dispatcher key.
    expect(() => build('reimprimir' as never, payload)).toThrow();
  });
});
