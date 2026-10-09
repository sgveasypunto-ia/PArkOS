/**
 * Unit tests for F7.3 — Tiquete de salida CU-15S byte-level fixtures.
 *
 * Covers the 19 conceptual fields per `plan.md:1789-1807` — see REQ-OPS-158.
 * The ticket is the common 80 mm format (48 columns, easypunto logos, NO QR):
 * the former QR + logo markers were removed on purpose.
 *
 * The 19-key byte-presence table mirrors the spec field list:
 *   1. Encabezado       (payload.sucursal.encabezado — DEC-SUC-28 dynamic)
 *   2. Empresa          (payload.empresa.nombre)
 *   3. Dirección        (payload.empresa.direccion)
 *   4. NIT              (payload.empresa.nit)
 *   5. Régimen          (payload.empresa.regimen)
 *   6. Operario         (payload.operario)
 *   7. Sello            (literal "*** SALIDA ***", bold and centred)
 *   7b. Tipo de operación (literal "Tipo: ROTACIÓN", bold — pedido del operador)
 *   8. Folio            (payload.folio)
 *   9. Tarifa aplicada  (copPlano(payload.tarifaAplicada) + "/hora")
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
  formatFecha,
  formatHora,
  type SalidaPayload,
} from '../escposTemplates';
import { copPlano } from './copPlano';
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
  it('T1 — emits all 19 CU-15S conceptual fields', () => {
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
    // 7b. Tipo de operación (pedido del operador — campo nuevo)
    expect(buf.indexOf(Buffer.from('Tipo: ROTACIÓN'))).toBeGreaterThanOrEqual(0);
    // 8. Folio
    expect(buf.indexOf(Buffer.from(`Folio: ${payload.folio}`))).toBeGreaterThanOrEqual(0);
    // 9. Tarifa aplicada
    expect(
      buf.indexOf(
        Buffer.from(`Tarifa: ${copPlano(payload.tarifaAplicada)}/hora`),
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
      buf.indexOf(Buffer.from(`Subtotal: ${copPlano(payload.subtotal)}`)),
    ).toBeGreaterThanOrEqual(0);
    // 15. IVA
    expect(
      buf.indexOf(Buffer.from(`IVA: ${copPlano(payload.iva)}`)),
    ).toBeGreaterThanOrEqual(0);
    // 16. TOTAL
    expect(
      buf.indexOf(Buffer.from(`TOTAL: ${copPlano(payload.total)}`)),
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
    // 80 mm: no QR / logo markers (intentional change)
    expect(buf.indexOf(Buffer.from(';QR:'))).toBe(-1);
    expect(buf.indexOf(Buffer.from(';LOGO:'))).toBe(-1);
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
// T3 — 80 mm format: brand logos, no QR
// ──────────────────────────────────────────────────────────────────────────

describe('buildSalidaBuffer — 80 mm format', () => {
  it('T3 — no QR marker nor QR command; the easypunto brand opens and closes the ticket', () => {
    const buf = build('salida', makeSalidaPayload());
    expect(buf.indexOf(Buffer.from(';QR:'))).toBe(-1);
    expect(buf.indexOf(Buffer.from([0x1d, 0x28, 0x6b]))).toBe(-1);
    expect(buf.toString('utf8').match(/easypunto/g)).toHaveLength(2);
  });

  it('sello "*** SALIDA ***" is bold (ESC E 1 ... ESC E 0), never 2x text (ESC ! n)', () => {
    const buf = build('salida', makeSalidaPayload());
    const boldOn = buf.lastIndexOf(Buffer.from([0x1b, 0x45, 0x01]), buf.indexOf(Buffer.from('*** SALIDA ***')));
    const selloIdx = buf.indexOf(Buffer.from('*** SALIDA ***'));
    expect(boldOn).toBeGreaterThanOrEqual(0);
    expect(selloIdx).toBeGreaterThan(boldOn);
    expect(buf.indexOf(Buffer.from([0x1b, 0x45, 0x00]), selloIdx)).toBeGreaterThan(selloIdx);
    expect(buf.indexOf(Buffer.from([0x1b, 0x21]))).toBe(-1);
  });
});
