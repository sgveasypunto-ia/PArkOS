/**
 * Unit tests for F7.3 — Tiquete de salida CU-15S byte-level fixtures.
 *
 * Covers the 19 conceptual fields per `plan.md:1789-1807` + the 2
 * DEC-SUC-26 additions (QR + logo) — see REQ-OPS-158.
 *
 * The 19-key byte-presence table mirrors the spec field list:
 *   1. Encabezado       (payload.sucursal.encabezado — DEC-SUC-28 dynamic)
 *   2. Empresa          (payload.empresa.nombre)
 *   3. Dirección        (payload.empresa.direccion)
 *   4. NIT              (payload.empresa.nit)
 *   5. Régimen          (payload.empresa.regimen)
 *   6. Operario         (payload.operario)
 *   7. Sello            (literal "*** SALIDA ***" wrapped by escText2x/escTextReset)
 *   8. Folio            (payload.folio)
 *   9. Tarifa aplicada  (formatCOP(payload.tarifaAplicada) + "/hora")
 *  10. Fecha            (date-only, dd/MM/yyyy)
 *  11. Hora entrada     (HH:mm)
 *  12. Hora salida      (HH:mm)
 *  13. Tiempo total     (payload.tiempoTotal)
 *  14. Subtotal         (formatCOP)
 *  15. IVA              (formatCOP)
 *  16. TOTAL            (formatCOP, bold)
 *  17. Medio de pago    (payload.medioPago)
 *  18. Placa            (payload.placa)
 *  19. Póliza RC / Resolución FE / Observaciones (compound)
 *
 * Drift guard (DEC-SUC-28): the F5.2 constant "PARKINGOS" MUST be
 * absent from the buffer — `payload.sucursal.encabezado` replaces it.
 */
import { describe, it, expect } from 'vitest';

import { build } from '../escposBuilder';
import {
  formatCOP,
  formatFecha,
  formatHora,
  type SalidaPayload,
} from '../escposTemplates';
import { validSalidaPayload } from './escposBuilder.test';

// ──────────────────────────────────────────────────────────────────────────
// Fixture — full SalidaPayload with sucursal.encabezado
// ──────────────────────────────────────────────────────────────────────────

function makeSalidaPayload(overrides?: Partial<SalidaPayload>): SalidaPayload {
  return {
    ...validSalidaPayload(),
    sucursal: { encabezado: 'Sucursal Norte' },
    ...overrides,
  } as SalidaPayload;
}

// ──────────────────────────────────────────────────────────────────────────
// T1 — 19-field byte presence (REQ-OPS-158)
// ──────────────────────────────────────────────────────────────────────────

describe('buildSalidaBuffer — CU-15S 19-field byte presence (HU-F7.3 / REQ-OPS-158)', () => {
  it('T1 — emits all 19 CU-15S conceptual fields + QR + logo markers', () => {
    const payload = makeSalidaPayload();
    const buf = build('salida', payload);

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
    // 7. Sello "*** SALIDA ***"
    expect(buf.indexOf(Buffer.from('*** SALIDA ***'))).toBeGreaterThanOrEqual(0);
    // 8. Folio
    expect(buf.indexOf(Buffer.from(`Folio: ${payload.folio}`))).toBeGreaterThanOrEqual(0);
    // 9. Tarifa aplicada
    expect(
      buf.indexOf(
        Buffer.from(`Tarifa: ${formatCOP(payload.tarifaAplicada)}/hora`),
      ),
    ).toBeGreaterThanOrEqual(0);
    // 10. Fecha (date-only)
    expect(
      buf.indexOf(
        Buffer.from(`Fecha: ${formatFecha(payload.fechaEntrada)}`),
      ),
    ).toBeGreaterThanOrEqual(0);
    // 11. Hora entrada
    expect(
      buf.indexOf(
        Buffer.from(`Hora entrada: ${formatHora(payload.fechaEntrada)}`),
      ),
    ).toBeGreaterThanOrEqual(0);
    // 12. Hora salida
    expect(
      buf.indexOf(
        Buffer.from(`Hora salida: ${formatHora(payload.fechaSalida)}`),
      ),
    ).toBeGreaterThanOrEqual(0);
    // 13. Tiempo total
    expect(
      buf.indexOf(Buffer.from(`Tiempo: ${payload.tiempoTotal}`)),
    ).toBeGreaterThanOrEqual(0);
    // 14. Subtotal
    expect(
      buf.indexOf(Buffer.from(`Subtotal: ${formatCOP(payload.subtotal)}`)),
    ).toBeGreaterThanOrEqual(0);
    // 15. IVA
    expect(
      buf.indexOf(Buffer.from(`IVA: ${formatCOP(payload.iva)}`)),
    ).toBeGreaterThanOrEqual(0);
    // 16. TOTAL
    expect(
      buf.indexOf(Buffer.from(`TOTAL: ${formatCOP(payload.total)}`)),
    ).toBeGreaterThanOrEqual(0);
    // 17. Medio de pago
    expect(
      buf.indexOf(Buffer.from(`Medio de pago: ${payload.medioPago}`)),
    ).toBeGreaterThanOrEqual(0);
    // 18. Placa
    expect(buf.indexOf(Buffer.from(`Placa: ${payload.placa}`))).toBeGreaterThanOrEqual(0);
    // 19a. Horario atención
    expect(
      buf.indexOf(Buffer.from(`Horario: ${payload.horarioAtencion}`)),
    ).toBeGreaterThanOrEqual(0);
    // 19b. Póliza RC (optional, but validSalidaPayload has it)
    expect(
      buf.indexOf(Buffer.from(`Poliza RC: ${payload.polizaRC}`)),
    ).toBeGreaterThanOrEqual(0);
    // 19c. Resolución FE
    expect(
      buf.indexOf(Buffer.from(`Resolucion FE: ${payload.resolucionFE}`)),
    ).toBeGreaterThanOrEqual(0);
    // DEC-SUC-26 — QR + logo markers
    expect(buf.indexOf(Buffer.from(';QR:'))).toBeGreaterThanOrEqual(0);
    expect(buf.indexOf(Buffer.from(';LOGO:'))).toBeGreaterThanOrEqual(0);
  });

  it('T1.optional — emits "Observaciones:" when payload has observaciones', () => {
    const payload = makeSalidaPayload({ observaciones: 'Sin novedad' });
    const buf = build('salida', payload);
    expect(buf.indexOf(Buffer.from('Observaciones: Sin novedad'))).toBeGreaterThanOrEqual(0);
  });

  it('T1.drift — full canonical field-ordering (Encabezado first, Sello after Operario)', () => {
    const payload = makeSalidaPayload();
    const buf = build('salida', payload);
    const headerIdx = buf.indexOf(Buffer.from(payload.sucursal.encabezado));
    const operarioIdx = buf.indexOf(Buffer.from(`Operario: ${payload.operario}`));
    const selloIdx = buf.indexOf(Buffer.from('*** SALIDA ***'));
    expect(headerIdx).toBeGreaterThanOrEqual(0);
    expect(operarioIdx).toBeGreaterThan(headerIdx);
    expect(selloIdx).toBeGreaterThan(operarioIdx);
  });
});

// ──────────────────────────────────────────────────────────────────────────
// T2 — Dynamic header (DEC-SUC-28)
// ──────────────────────────────────────────────────────────────────────────

describe('buildSalidaBuffer — DEC-SUC-28 dynamic header', () => {
  it('T2 — buffer contains payload.sucursal.encabezado, NOT "PARKINGOS"', () => {
    const payload = makeSalidaPayload({
      sucursal: { encabezado: 'Sucursal Norte' },
    });
    const buf = build('salida', payload);
    expect(buf.indexOf(Buffer.from('Sucursal Norte'))).toBeGreaterThanOrEqual(0);
    // Drift guard: F5.2 constant "PARKINGOS" MUST NOT appear in the buffer.
    expect(buf.indexOf(Buffer.from('PARKINGOS'))).toBe(-1);
  });

  it('T2.alternate — buffer contains alternate sucursal.encabezado value verbatim', () => {
    const payload = makeSalidaPayload({
      sucursal: { encabezado: 'Sucursal Sur — Bogota' },
    });
    const buf = build('salida', payload);
    expect(buf.indexOf(Buffer.from('Sucursal Sur — Bogota'))).toBeGreaterThanOrEqual(0);
  });
});

// ──────────────────────────────────────────────────────────────────────────
// T3 — QR marker (DEC-SUC-26)
// ──────────────────────────────────────────────────────────────────────────

describe('buildSalidaBuffer — DEC-SUC-26 QR marker', () => {
  it('T3 — buffer contains ";QR:" text marker + the qrDataUrl payload verbatim', () => {
    const payload = makeSalidaPayload();
    const buf = build('salida', payload);
    expect(buf.indexOf(Buffer.from(';QR:'))).toBeGreaterThanOrEqual(0);
    expect(buf.indexOf(Buffer.from(payload.qrDataUrl))).toBeGreaterThanOrEqual(0);
    expect(
      buf.indexOf(Buffer.from(`;QR:${payload.qrDataUrl}`)),
    ).toBeGreaterThanOrEqual(0);
  });
});

// ──────────────────────────────────────────────────────────────────────────
// T4 — Logo marker (DEC-SUC-26)
// ──────────────────────────────────────────────────────────────────────────

describe('buildSalidaBuffer — DEC-SUC-26 logo marker', () => {
  it('T4 — buffer contains ";LOGO:" text marker + cached logo ("OK" sentinel)', () => {
    const payload = makeSalidaPayload();
    const buf = build('salida', payload);
    expect(buf.indexOf(Buffer.from(';LOGO:'))).toBeGreaterThanOrEqual(0);
    // validSalidaPayload() has logoDataUrl='data:image/png;base64,BBB' (non-empty)
    // → builder emits "OK" sentinel (text marker — actual rasterization is
    // the caller's responsibility per F5.2 R4 purity).
    expect(buf.indexOf(Buffer.from(';LOGO:OK'))).toBeGreaterThanOrEqual(0);
  });

  it('T4.fallback — buffer contains placeholder glyph ▢ when logoDataUrl is empty', () => {
    const payload = makeSalidaPayload({ logoDataUrl: '' });
    const buf = build('salida', payload);
    // ▢ placeholder glyph (DEC-SUC-08 documented "logo missing" sentinel)
    expect(buf.indexOf(Buffer.from('\u25A2'))).toBeGreaterThanOrEqual(0);
    expect(buf.indexOf(Buffer.from(';LOGO:\u25A2'))).toBeGreaterThanOrEqual(0);
  });
});

// ──────────────────────────────────────────────────────────────────────────
// Sello wrap — F7.3 locks the escText2x/escTextReset invariant
// ──────────────────────────────────────────────────────────────────────────

describe('buildSalidaBuffer — sello wrap (DEC-SUC-04 + DEC-SUC-27)', () => {
  it('emits "*** SALIDA ***" preceded by 0x1B 0x21 0x30 and followed by 0x1B 0x21 0x00', () => {
    const payload = makeSalidaPayload();
    const buf = build('salida', payload);
    const text2xIdx = buf.indexOf(Buffer.from([0x1b, 0x21, 0x30]));
    const selloIdx = buf.indexOf(Buffer.from('*** SALIDA ***'));
    const textResetIdx = buf.indexOf(
      Buffer.from([0x1b, 0x21, 0x00]),
      text2xIdx + 3, // search starts AFTER the 0x1B 0x21 0x30 opcode
    );
    expect(text2xIdx).toBeGreaterThanOrEqual(0);
    expect(selloIdx).toBeGreaterThan(text2xIdx);
    expect(textResetIdx).toBeGreaterThan(selloIdx);
  });
});
