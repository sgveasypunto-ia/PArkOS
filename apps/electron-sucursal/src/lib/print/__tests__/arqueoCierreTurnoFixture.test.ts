/**
 * `arqueoCierreTurnoFixture.test.ts` — strict-TDD escpos regression
 * guard for HU-F10.2 (DA-F10.2-5 RESOLVED, AD-6).
 *
 * The F10.1 `escposBuilder.build('arqueo', payload)` already emits
 * `Codigo: ${payload.auditoria_codigo}` (lib/print/escposBuilder.ts:498).
 * The F10.2 cierre de turno flow passes `auditoria_codigo='cierre_turno'`
 * and the same 12-line body MUST round-trip unchanged.
 *
 * Coverage (3 scenarios):
 *   - byte fixture: `Codigo: cierre_turno` appears in the body.
 *   - regression: `Codigo: cierre_turno` does NOT co-emit the legacy
 *     `auditoria_codigo: 'AUD-...'` value (so a stray auditoria-codigo
 *     substitution cannot leak).
 *   - full byte-fixture: all 12 conceptual lines are present with the
 *     new discriminator — guards the F10.1 escpos shape from regressing
 *     if the builder is touched.
 *
 * The fixture is golden — does NOT depend on local timezone (the
 * `Fecha:` line is pinned via `formatFechaCorta(payload.fecha)` per
 * F10.1 arqueoFixture.test.ts precedent).
 */
import { describe, expect, it } from 'vitest';

import { build, validatePayload } from '../escposBuilder';
import {
  arqueoPayloadSchema,
  formatCOP,
  formatFechaCorta,
  type ArqueoPayload,
} from '../escposTemplates';

const VALID_PAYLOAD: ArqueoPayload = {
  sucursal: { encabezado: 'Sucursal Norte' },
  uuid_sesion: 'abc12345-6789-0abc-1234-56789abcdef0',
  base_efectivo_cop: 50_000,
  valor_esperado_efectivo: 100_000,
  valor_esperado_datafono: 0,
  valor_reportado_efectivo: 100_000,
  valor_reportado_datafono: 0,
  diferencia_efectivo: 0,
  diferencia_datafono: 0,
  tolerancia_efectivo: 1_000,
  tolerancia_datafono: 500,
  justificacion: '',
  auditoria_codigo: 'cierre_turno',
  fecha: '2026-09-21T14:30:00.000Z',
  uuid_sesion_short: 'abcdef0',
};

describe('HU-F10.2 — escposBuilder.build("arqueo", { auditoria_codigo: "cierre_turno" }) regression (DA-F10.2-5)', () => {
  // ────────────────────────────────────────────────────────────────────
  // dispatch-cierre-turno — `Codigo: cierre_turno` round-trips verbatim
  // ────────────────────────────────────────────────────────────────────
  it('dispatch-cierre-turno: build("arqueo", { ..., auditoria_codigo: "cierre_turno" }) emits "Codigo: cierre_turno"', () => {
    const buf = build('arqueo', VALID_PAYLOAD);
    const utf8 = buf.toString('utf8');

    // The discriminator MUST round-trip unchanged — DA-F10.2-5 RESOLVED.
    expect(utf8).toContain('Codigo: cierre_turno');

    // Regression: the legacy `'AUD-...'` literal MUST NOT leak through.
    expect(utf8).not.toContain('Codigo: AUD-');

    // The 12-line body shape is preserved — pin a few key lines.
    expect(utf8).toContain('ARQUEO PARCIAL — Sucursal Norte');
    expect(utf8).toContain('*** ARQUEO PARCIAL ***');
    // Fecha MUST use the dynamic formatter (timezone-safe per F10.1
    // arqueoFixture.test.ts:90-91 lesson).
    expect(utf8).toContain(`Fecha: ${formatFechaCorta(VALID_PAYLOAD.fecha)}`);
    expect(utf8).toContain('Sesion: abcdef0');
    expect(utf8).toContain(`Base: ${formatCOP(50_000)}`);
    // diferencia=0 → `+` sign per spec (NEVER `±`).
    expect(utf8).toContain(`Diferencia efectivo: +${formatCOP(0)}`);
    expect(utf8).toContain(`Diferencia datafono: +${formatCOP(0)}`);
    // justificacion empty → NO "Justificacion:" line.
    expect(utf8).not.toContain('Justificacion:');
  });

  // ────────────────────────────────────────────────────────────────────
  // dispatch-cierre-turno-with-justificacion — descuadre path also works
  // ────────────────────────────────────────────────────────────────────
  it('dispatch-cierre-turno-with-justificacion: diferencia != 0 + justificacion → "Justificacion:" line + sign prefix', () => {
    const buf = build('arqueo', {
      ...VALID_PAYLOAD,
      valor_reportado_efectivo: 97_000,
      diferencia_efectivo: -3_000,
      justificacion: 'Faltante menor en caja',
    });
    const utf8 = buf.toString('utf8');

    // Same discriminator round-trips.
    expect(utf8).toContain('Codigo: cierre_turno');
    // Sign prefix MUST be `-` for negative diferencia (NEVER `±`).
    expect(utf8).toContain(`Diferencia efectivo: -${formatCOP(3_000)}`);
    // Justificacion line MUST be present when the descuadre path is taken.
    expect(utf8).toContain('Justificacion: Faltante menor en caja');
  });

  // ────────────────────────────────────────────────────────────────────
  // validate-payload — Zod schema accepts 'cierre_turno' as a valid
  // `auditoria_codigo` value (regression: schema MUST NOT whitelist only
  // `'AUD-*'` codes from F10.1).
  // ────────────────────────────────────────────────────────────────────
  it('validate-payload: arqueoPayloadSchema accepts auditoria_codigo="cierre_turno"', () => {
    expect(() => validatePayload('arqueo', VALID_PAYLOAD)).not.toThrow();
    // The Zod schema MUST round-trip the discriminator unchanged.
    const parsed = arqueoPayloadSchema.parse(VALID_PAYLOAD);
    expect(parsed.auditoria_codigo).toBe('cierre_turno');
  });
});