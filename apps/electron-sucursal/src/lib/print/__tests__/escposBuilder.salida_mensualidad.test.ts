/**
 * Unit tests for F7.3 — Tiquete de salida-mensualidad CU-15SM byte-level fixtures.
 *
 * Covers the 15 conceptual fields per `plan.md:1810` + the 2
 * DEC-SUC-26 additions (QR + logo) + the DEC-SUC-27 sello invariant
 * (`*** PAGO CON MENSUALIDAD ***` wrapped by `escText2x()` /
 * `escTextReset()`) — see REQ-OPS-159.
 *
 * The 15-key byte-presence table:
 *   1. Encabezado       (payload.sucursal.encabezado — DEC-SUC-28 dynamic)
 *   2. Empresa          (payload.empresa.nombre)
 *   3. Dirección        (payload.empresa.direccion)
 *   4. NIT              (payload.empresa.nit)
 *   5. Régimen          (payload.empresa.regimen)
 *   6. Operario         (payload.operario)
 *   7. Sello            (literal "*** PAGO CON MENSUALIDAD ***" wrapped by
 *                        escText2x [0x1B 0x21 0x30] + escTextReset [0x1B 0x21 0x00])
 *   8. Folio            (payload.folio)
 *   9. Fecha            (date-only, dd/MM/yyyy)
 *  10. Hora entrada     (HH:mm)
 *  11. Hora salida      (HH:mm)
 *  12. Tiempo total     (payload.tiempoTotal)
 *  13. Placa            (payload.placa)
 *  14. Horario atención (payload.horarioAtencion)
 *  15. Póliza RC / Resolución FE / Observaciones (compound)
 *
 * NO monetary fields (DEC-SUC-23) — the mensualidad fee is settled by the
 * subscription, NOT the exit. Drift guard: `Subtotal:`, `IVA:`,
 * `TOTAL:`, `Medio de pago:` MUST NOT appear.
 */
import { describe, it, expect } from 'vitest';

import { build } from '../escposBuilder';
import {
  formatFecha,
  formatHora,
  type SalidaMensualidadPayload,
} from '../escposTemplates';
import { validSalidaPayload } from './escposBuilder.test';

// ──────────────────────────────────────────────────────────────────────────
// Fixtures
// ──────────────────────────────────────────────────────────────────────────

function makeValidSalidaPayload(): ReturnType<typeof validSalidaPayload> {
  return validSalidaPayload();
}

function makeSalidaMensualidadPayload(
  overrides?: Partial<SalidaMensualidadPayload>,
): SalidaMensualidadPayload {
  return {
    placa: 'ABC12D',
    fechaEntrada: '2026-09-01T00:00:00Z',
    fechaSalida: '2026-09-16T08:00:00Z',
    qrDataUrl: 'data:image/png;base64,CCC',
    logoDataUrl: 'data:image/png;base64,DDD',
    empresa: {
      nombre: 'Parkos Demo S.A.S.',
      nit: '900123456-7',
      direccion: 'Calle 1 #2-3, Bogota',
      regimen: 'Responsable de IVA',
    },
    operario: 'op-002',
    horarioAtencion: '24 horas',
    polizaRC: 'POL-99999',
    folio: '00000000-0000-4000-8000-000000000007',
    observaciones: 'Mensualidad vigente',
    sucursal: { encabezado: 'Sucursal Sur' },
    tiempoTotal: '360h 00m',
    esMensualidad: true,
    ...overrides,
  } as SalidaMensualidadPayload;
}

// ──────────────────────────────────────────────────────────────────────────
// T5 — 15-field byte presence (REQ-OPS-159)
// ──────────────────────────────────────────────────────────────────────────

describe('buildSalidaMensualidadBuffer — CU-15SM 15-field byte presence (HU-F7.3 / REQ-OPS-159)', () => {
  it('T5 — emits all 15 CU-15SM conceptual fields + QR + logo markers', () => {
    const payload = makeSalidaMensualidadPayload();
    const buf = build('salida-mensualidad', payload);

    // 1. Encabezado (dynamic, per DEC-SUC-28)
    expect(buf.indexOf(Buffer.from(payload.sucursal.encabezado))).toBeGreaterThanOrEqual(0);
    // 2. Empresa
    expect(buf.indexOf(Buffer.from(payload.empresa.nombre))).toBeGreaterThanOrEqual(0);
    // 3. Dirección
    expect(buf.indexOf(Buffer.from(payload.empresa.direccion))).toBeGreaterThanOrEqual(0);
    // 4. NIT
    expect(buf.indexOf(Buffer.from(`NIT ${payload.empresa.nit}`))).toBeGreaterThanOrEqual(0);
    // 5. Régimen
    expect(buf.indexOf(Buffer.from(payload.empresa.regimen))).toBeGreaterThanOrEqual(0);
    // 6. Operario
    expect(buf.indexOf(Buffer.from(`Operario: ${payload.operario}`))).toBeGreaterThanOrEqual(0);
    // 7. Sello "*** PAGO CON MENSUALIDAD ***"
    expect(buf.indexOf(Buffer.from('*** PAGO CON MENSUALIDAD ***'))).toBeGreaterThanOrEqual(0);
    // 8. Folio
    expect(buf.indexOf(Buffer.from(`Folio: ${payload.folio}`))).toBeGreaterThanOrEqual(0);
    // 9. Fecha (date-only)
    expect(
      buf.indexOf(
        Buffer.from(`Fecha: ${formatFecha(payload.fechaEntrada)}`),
      ),
    ).toBeGreaterThanOrEqual(0);
    // 10. Hora entrada
    expect(
      buf.indexOf(
        Buffer.from(`Hora entrada: ${formatHora(payload.fechaEntrada)}`),
      ),
    ).toBeGreaterThanOrEqual(0);
    // 11. Hora salida
    expect(
      buf.indexOf(
        Buffer.from(`Hora salida: ${formatHora(payload.fechaSalida)}`),
      ),
    ).toBeGreaterThanOrEqual(0);
    // 12. Tiempo total
    expect(
      buf.indexOf(Buffer.from(`Tiempo: ${payload.tiempoTotal}`)),
    ).toBeGreaterThanOrEqual(0);
    // 13. Placa
    expect(buf.indexOf(Buffer.from(`Placa: ${payload.placa}`))).toBeGreaterThanOrEqual(0);
    // 14. Horario atención
    expect(
      buf.indexOf(Buffer.from(`Horario: ${payload.horarioAtencion}`)),
    ).toBeGreaterThanOrEqual(0);
    // 15a. Póliza RC (optional but in fixture)
    expect(
      buf.indexOf(Buffer.from(`Poliza RC: ${payload.polizaRC}`)),
    ).toBeGreaterThanOrEqual(0);
    // 15b. Observaciones
    expect(
      buf.indexOf(Buffer.from(`Observaciones: ${payload.observaciones}`)),
    ).toBeGreaterThanOrEqual(0);
    // DEC-SUC-26 — QR + logo markers
    expect(buf.indexOf(Buffer.from(';QR:'))).toBeGreaterThanOrEqual(0);
    expect(buf.indexOf(Buffer.from(';LOGO:'))).toBeGreaterThanOrEqual(0);
  });
});

// ──────────────────────────────────────────────────────────────────────────
// T6 — Sello byte sequence (DEC-SUC-27 invariant)
// ──────────────────────────────────────────────────────────────────────────

describe('buildSalidaMensualidadBuffer — sello opcode sequence (DEC-SUC-27)', () => {
  it('T6 — "*** PAGO CON MENSUALIDAD ***" preceded by 0x1B 0x21 0x30 and followed by 0x1B 0x21 0x00', () => {
    const payload = makeSalidaMensualidadPayload();
    const buf = build('salida-mensualidad', payload);
    const text2xIdx = buf.indexOf(Buffer.from([0x1b, 0x21, 0x30]));
    const selloIdx = buf.indexOf(Buffer.from('*** PAGO CON MENSUALIDAD ***'));
    const textResetIdx = buf.indexOf(
      Buffer.from([0x1b, 0x21, 0x00]),
      text2xIdx + 3, // search starts AFTER the 0x1B 0x21 0x30 opcode
    );
    expect(text2xIdx).toBeGreaterThanOrEqual(0);
    expect(selloIdx).toBeGreaterThan(text2xIdx);
    expect(textResetIdx).toBeGreaterThan(selloIdx);
  });

  it('T6.distinct — CU-15SM sello MUST NOT appear in CU-15S buffer (separate rutas)', () => {
    const buf = build(
      'salida',
      makeValidSalidaPayload(), // Import from salida.test.ts scope
    );
    expect(buf.indexOf(Buffer.from('PAGO CON MENSUALIDAD'))).toBe(-1);
  });
});

// ──────────────────────────────────────────────────────────────────────────
// T7 — NO monetary fields (DEC-SUC-23 invariant)
// ──────────────────────────────────────────────────────────────────────────

describe('buildSalidaMensualidadBuffer — DEC-SUC-23 (no monetary fields)', () => {
  it('T7 — buffer does NOT contain "Subtotal:", "IVA:", "TOTAL:", "Medio de pago:"', () => {
    const payload = makeSalidaMensualidadPayload();
    const buf = build('salida-mensualidad', payload);
    expect(buf.indexOf(Buffer.from('Subtotal:'))).toBe(-1);
    expect(buf.indexOf(Buffer.from('IVA:'))).toBe(-1);
    expect(buf.indexOf(Buffer.from('TOTAL:'))).toBe(-1);
    expect(buf.indexOf(Buffer.from('Medio de pago:'))).toBe(-1);
  });

  it('T7.strict — buffer does NOT contain "$" character (no currency symbol at all)', () => {
    const payload = makeSalidaMensualidadPayload();
    const buf = build('salida-mensualidad', payload);
    expect(buf.indexOf(Buffer.from('$'))).toBe(-1);
  });
});

// ──────────────────────────────────────────────────────────────────────────
// DEC-SUC-28 dynamic header — CU-15SM path also swaps PARKINGOS
// ──────────────────────────────────────────────────────────────────────────

describe('buildSalidaMensualidadBuffer — DEC-SUC-28 dynamic header', () => {
  it('emits payload.sucursal.encabezado, NOT "PARKINGOS"', () => {
    const payload = makeSalidaMensualidadPayload({
      sucursal: { encabezado: 'Sucursal Sur' },
    });
    const buf = build('salida-mensualidad', payload);
    expect(buf.indexOf(Buffer.from('Sucursal Sur'))).toBeGreaterThanOrEqual(0);
    expect(buf.indexOf(Buffer.from('PARKINGOS'))).toBe(-1);
  });
});

// ──────────────────────────────────────────────────────────────────────────
// QR + logo markers (DEC-SUC-26)
// ──────────────────────────────────────────────────────────────────────────

describe('buildSalidaMensualidadBuffer — DEC-SUC-26 QR + logo', () => {
  it('emits ";QR:" marker with qrDataUrl payload verbatim', () => {
    const payload = makeSalidaMensualidadPayload();
    const buf = build('salida-mensualidad', payload);
    expect(
      buf.indexOf(Buffer.from(`;QR:${payload.qrDataUrl}`)),
    ).toBeGreaterThanOrEqual(0);
  });

  it('emits ";LOGO:OK" marker when logoDataUrl is non-empty (cached logo)', () => {
    const payload = makeSalidaMensualidadPayload();
    const buf = build('salida-mensualidad', payload);
    expect(buf.indexOf(Buffer.from(';LOGO:OK'))).toBeGreaterThanOrEqual(0);
  });

  it('emits ";LOGO:▢" placeholder glyph when logoDataUrl is empty (cold cache)', () => {
    const payload = makeSalidaMensualidadPayload({ logoDataUrl: '' });
    const buf = build('salida-mensualidad', payload);
    expect(buf.indexOf(Buffer.from(';LOGO:\u25A2'))).toBeGreaterThanOrEqual(0);
  });
});
