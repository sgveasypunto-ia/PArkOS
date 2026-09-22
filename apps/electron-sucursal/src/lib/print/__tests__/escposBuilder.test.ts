/**
 * Unit tests for `escposBuilder.ts` (HU-F5.2 / F6.2).
 *
 * Covers:
 *   - 5 byte-level ESC/POS opcode fixtures (init / cut / center / bold / 2x).
 *   - `EscposInvalidTipoError` carries `code` and `given`.
 *   - Payload missing required field throws `EscposPayloadMissingFieldError`.
 *   - `build()` is pure — does NOT call `window.print()` (no DOM side effects).
 *   - `formatCOP` inline copy: `100000` → `"$ 100.000"` (es-CO, 0 decimales).
 *
 * F6.2 — `entradaPayloadSchema` tightened qr + logo to REQUIRED (F5.2
 * shipped them as `.optional()`). The exported `validEntradaPayload()`
 * fixture provides both keys verbatim, so the existing scenarios
 * continue to pass against the strict schema. The dedicated 17-byte
 * presence scenarios live in `escposBuilder.entrada.test.ts`.
 */
import { describe, it, expect, vi } from 'vitest';

import {
  build,
  escInit,
  escCenter,
  escBoldOn,
  escText2x,
  cutPartial,
  EscposInvalidTipoError,
  EscposPayloadMissingFieldError,
  isTiqueteTipo,
} from '../escposBuilder';
import { formatCOP } from '../escposTemplates';

// ──────────────────────────────────────────────────────────────────────────
// Byte-level fixtures
// ──────────────────────────────────────────────────────────────────────────

describe('escposBuilder byte fixtures', () => {
  it('esc_init returns Buffer [0x1B, 0x40]', () => {
    expect(escInit()).toEqual(Buffer.from([0x1b, 0x40]));
  });

  it('esc_center returns Buffer [0x1B, 0x61, 0x01]', () => {
    expect(escCenter()).toEqual(Buffer.from([0x1b, 0x61, 0x01]));
  });

  it('esc_bold_on returns Buffer [0x1B, 0x45]', () => {
    expect(escBoldOn()).toEqual(Buffer.from([0x1b, 0x45]));
  });

  it('esc_text_2x returns Buffer [0x1B, 0x21, 0x30]', () => {
    expect(escText2x()).toEqual(Buffer.from([0x1b, 0x21, 0x30]));
  });

  it('cut_partial returns Buffer [0x1D, 0x56, 0x00]', () => {
    expect(cutPartial()).toEqual(Buffer.from([0x1d, 0x56, 0x00]));
  });
});

// ──────────────────────────────────────────────────────────────────────────
// formatCOP inline
// ──────────────────────────────────────────────────────────────────────────

describe('formatCOP inline copy (DEC-SUC-07)', () => {
  it('formats 100000 as "$ 100.000" (es-CO, 0 decimales)', () => {
    const result = formatCOP(100000);
    expect(result.replace(/\s/g, ' ')).toMatch(/^\$\s?100\.000$/);
  });

  it('formats 0 as "$ 0"', () => {
    const result = formatCOP(0);
    expect(result.replace(/\s/g, ' ')).toMatch(/^\$\s?0$/);
  });
});

// ──────────────────────────────────────────────────────────────────────────
// Error class discrimination
// ──────────────────────────────────────────────────────────────────────────

describe('EscposInvalidTipoError', () => {
  it('throws with code=escpos_invalid_tipo and given=bogus', () => {
    let captured: EscposInvalidTipoError | null = null;
    try {
      // Cast required: `TiqueteTipo` is a strict union; we intentionally
      // bypass it to exercise the runtime error path.
      build('foo-bar' as unknown as Parameters<typeof build>[0], {});
    } catch (err) {
      captured = err as EscposInvalidTipoError;
    }
    expect(captured).not.toBeNull();
    expect(captured).toBeInstanceOf(EscposInvalidTipoError);
    expect(captured!.code).toBe('escpos_invalid_tipo');
    expect(captured!.given).toBe('foo-bar');
    expect(captured!.message).toContain('foo-bar');
  });

  it('isTiqueteTipo narrows the 5-allowed union (F8.1 adds recibo_pago)', () => {
    expect(isTiqueteTipo('entrada')).toBe(true);
    expect(isTiqueteTipo('salida')).toBe(true);
    expect(isTiqueteTipo('salida-mensualidad')).toBe(true);
    expect(isTiqueteTipo('reimpresion')).toBe(true);
    expect(isTiqueteTipo('recibo_pago')).toBe(true);
    expect(isTiqueteTipo('FOO')).toBe(false);
    expect(isTiqueteTipo(123)).toBe(false);
    expect(isTiqueteTipo(null)).toBe(false);
    expect(isTiqueteTipo(undefined)).toBe(false);
  });
});

describe('EscposPayloadMissingFieldError', () => {
  it('throws with code=escpos_payload_missing_field and populated issues', () => {
    let captured: EscposPayloadMissingFieldError | null = null;
    try {
      build('entrada', { foo: 1 });
    } catch (err) {
      captured = err as EscposPayloadMissingFieldError;
    }
    expect(captured).not.toBeNull();
    expect(captured).toBeInstanceOf(EscposPayloadMissingFieldError);
    expect(captured!.code).toBe('escpos_payload_missing_field');
    expect(captured!.issues.length).toBeGreaterThan(0);
  });
});

// ──────────────────────────────────────────────────────────────────────────
// Purity
// ──────────────────────────────────────────────────────────────────────────

describe('escposBuilder purity', () => {
  it('build("entrada", payload) does NOT call window.print()', () => {
    const spy = vi.spyOn(window, 'print');
    const payload = validEntradaPayload();
    build('entrada', payload);
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });

  it('build("salida", payload) does NOT call window.print()', () => {
    const spy = vi.spyOn(window, 'print');
    const payload = validSalidaPayload();
    build('salida', payload);
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });
});

// ──────────────────────────────────────────────────────────────────────────
// Fixtures — minimal valid payloads (helpers, exported for use in
// escposBuilder.types.test.ts).
// ──────────────────────────────────────────────────────────────────────────

export function validEntradaPayload() {
  return {
    variant: 'con-placa' as const,
    placa: 'ABC123',
    fechaEntrada: '2026-09-16T08:30:00Z',
    qrDataUrl: 'data:image/png;base64,AAA',
    logoDataUrl: 'data:image/png;base64,BBB',
    empresa: {
      nombre: 'Parkos Demo S.A.S.',
      nit: '900123456-7',
      direccion: 'Calle 1 #2-3, Bogota',
      regimen: 'Responsable de IVA',
    },
    operario: 'op-001',
    tarifaAplicada: 5000,
    horarioAtencion: '24 horas',
    polizaRC: 'POL-12345',
    folio: '00000000-0000-4000-8000-000000000001',
    observaciones: 'Sin novedad',
    // F7.3 (DEC-SUC-28) — branch header replaces F5.2 "PARKINGOS" constant.
    sucursal: { encabezado: 'Sucursal Centro' },
  };
}

export function validSalidaPayload() {
  return {
    ...validEntradaPayload(),
    sucursal: { encabezado: 'Sucursal Norte' },
    fechaSalida: '2026-09-16T10:30:00Z',
    tiempoTotal: '2h 00m',
    subtotal: 10000,
    iva: 1900,
    total: 11900,
    medioPago: 'efectivo',
    resolucionFE: 'RES-1876',
  };
}

void vi;