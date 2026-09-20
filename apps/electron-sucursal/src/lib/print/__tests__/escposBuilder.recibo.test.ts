/**
 * Unit tests for F8.1 — Recibo de pago (post-pago print) byte-level
 * fixtures.
 *
 * The recibo de pago prints AFTER the CU-15S ticket (DEC-SUC-27
 * verbatim: "CU-15S print fires AFTER pago, then recibo de pago").
 * The recibo carries the SAME 19 CU-15S conceptual fields PLUS two
 * additions:
 *   - `numero_recibo` — backend F1.10 assigns
 *     `sucursal-YYYYMMDD-NNNNNN` (DEC-SUC-28 verbatim).
 *   - `medio_pago` (typed literal `efectivo` | `datafono`) —
 *     replaces the CU-15S `medioPago: z.string().min(1)` with a
 *     strict discriminator.
 *
 * Coverage (3 byte-level tests):
 *   R1: `build('recibo_pago', payload)` emits a `Buffer` containing
 *       "RECIBO DE PAGO" header + `numero_recibo` line +
 *       `Medio de pago: <typed-value>` line.
 *   R2: dynamic header — buffer contains
 *       `payload.sucursal.encabezado` and MUST NOT contain the F5.2
 *       "PARKINGOS" constant (DEC-SUC-28 drift guard, mirrors
 *       `escposBuilder.salida.test.ts::T2`).
 *   R3: same 19 CU-15S conceptual fields PLUS the additional
 *       `numero_recibo` + `medio_pago` lines.
 *
 * Drift guard (DEC-SUC-28): the F5.2 "PARKINGOS" constant MUST be
 * absent from the buffer.
 */
import { describe, it, expect } from 'vitest';

import { build } from '../escposBuilder';
import {
  formatCOP,
  formatFecha,
  formatHora,
  type ReciboPagoPayload,
} from '../escposTemplates';
import { validSalidaPayload } from './escposBuilder.test';

// ──────────────────────────────────────────────────────────────────────────
// Fixture — full ReciboPagoPayload (extends CU-15S with numero_recibo + medio_pago)
// ──────────────────────────────────────────────────────────────────────────

function makeReciboPagoPayload(overrides?: Partial<ReciboPagoPayload>): ReciboPagoPayload {
  return {
    ...validSalidaPayload(),
    sucursal: { encabezado: 'Sucursal Norte' },
    numero_recibo: 'sucursal-20260919-000001',
    medio_pago: 'efectivo',
    ...overrides,
  } as ReciboPagoPayload;
}

// ──────────────────────────────────────────────────────────────────────────
// T1 — Recibo-specific byte presence (REQ-OPS-167 + DEC-SUC-27 + DEC-SUC-28)
// ──────────────────────────────────────────────────────────────────────────

describe('buildReciboPagoBuffer — recibo de pago byte presence (HU-F8.1)', () => {
  it('T1 — emits "RECIBO DE PAGO" header + numero_recibo + medio_pago (efectivo)', () => {
    const payload = makeReciboPagoPayload();
    const buf = build('recibo_pago', payload);

    expect(buf.indexOf(Buffer.from('RECIBO DE PAGO'))).toBeGreaterThanOrEqual(0);
    expect(
      buf.indexOf(Buffer.from(`Numero de recibo: ${payload.numero_recibo}`)),
    ).toBeGreaterThanOrEqual(0);
    expect(
      buf.indexOf(Buffer.from(`Medio de pago: ${payload.medio_pago}`)),
    ).toBeGreaterThanOrEqual(0);
    expect(buf.indexOf(Buffer.from('efectivo'))).toBeGreaterThanOrEqual(0);
  });

  it('T1.alternate — datafono medio_pago round-trips verbatim', () => {
    const payload = makeReciboPagoPayload({ medio_pago: 'datafono' });
    const buf = build('recibo_pago', payload);

    expect(buf.indexOf(Buffer.from('datafono'))).toBeGreaterThanOrEqual(0);
    expect(
      buf.indexOf(Buffer.from(`Medio de pago: ${payload.medio_pago}`)),
    ).toBeGreaterThanOrEqual(0);
  });
});

// ──────────────────────────────────────────────────────────────────────────
// T2 — Dynamic header (DEC-SUC-28)
// ──────────────────────────────────────────────────────────────────────────

describe('buildReciboPagoBuffer — DEC-SUC-28 dynamic header', () => {
  it('T2 — buffer contains payload.sucursal.encabezado, NOT "PARKINGOS"', () => {
    const payload = makeReciboPagoPayload({
      sucursal: { encabezado: 'Sucursal Norte' },
    });
    const buf = build('recibo_pago', payload);
    expect(buf.indexOf(Buffer.from('Sucursal Norte'))).toBeGreaterThanOrEqual(0);
    // Drift guard: F5.2 constant "PARKINGOS" MUST NOT appear in the buffer.
    expect(buf.indexOf(Buffer.from('PARKINGOS'))).toBe(-1);
  });
});

// ──────────────────────────────────────────────────────────────────────────
// T3 — All 19 CU-15S conceptual fields + numero_recibo + medio_pago
// ──────────────────────────────────────────────────────────────────────────

describe('buildReciboPagoBuffer — same 19 CU-15S fields + numero_recibo + medio_pago', () => {
  it('T3 — emits the 19 CU-15S conceptual fields PLUS numero_recibo + medio_pago', () => {
    const payload = makeReciboPagoPayload();
    const buf = build('recibo_pago', payload);

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
    // 7. Sello
    expect(buf.indexOf(Buffer.from('RECIBO DE PAGO'))).toBeGreaterThanOrEqual(0);
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
    // 18. Placa
    expect(buf.indexOf(Buffer.from(`Placa: ${payload.placa}`))).toBeGreaterThanOrEqual(0);
    // 19a. Horario atención
    expect(
      buf.indexOf(Buffer.from(`Horario: ${payload.horarioAtencion}`)),
    ).toBeGreaterThanOrEqual(0);
    // 19c. Resolución FE
    expect(
      buf.indexOf(Buffer.from(`Resolucion FE: ${payload.resolucionFE}`)),
    ).toBeGreaterThanOrEqual(0);

    // DEC-SUC-26 — QR + logo markers (mirror CU-15S)
    expect(buf.indexOf(Buffer.from(';QR:'))).toBeGreaterThanOrEqual(0);
    expect(buf.indexOf(Buffer.from(';LOGO:'))).toBeGreaterThanOrEqual(0);

    // Recibo-specific additions
    expect(
      buf.indexOf(Buffer.from(`Numero de recibo: ${payload.numero_recibo}`)),
    ).toBeGreaterThanOrEqual(0);
    expect(
      buf.indexOf(Buffer.from(`Medio de pago: ${payload.medio_pago}`)),
    ).toBeGreaterThanOrEqual(0);
  });
});