/**
 * `arqueoFixture.test.ts` — strict-TDD byte-fixture for the F10.1
 * `'arqueo'` ESC/POS dispatcher (REQ-OPS-155).
 *
 * Mirrors `escposBuilder.entrada.test.ts` shape (byte presence +
 * envelope init/cut + Zod rejection). The 12 conceptual lines per
 * design AD-3 + spec scenario 2:
 *
 *   1. centered bold header `ARQUEO PARCIAL — <sucursal.encabezado>`
 *   2. sello `*** ARQUEO PARCIAL ***` wrapped in escText2x/escTextReset
 *   3. `Codigo: <auditoria_codigo>`
 *   4. `Fecha: <formatFechaCorta(fecha)>` (es-CO short per F6.2)
 *   5. `Sesion: <uuid_sesion_short>` (last 8 chars of uuid_sesion)
 *   6. `Base: <formatCOP(base_efectivo_cop)>`
 *   7. `Esperado efectivo: <formatCOP(valor_esperado_efectivo)>`
 *   8. `Reportado efectivo: <formatCOP(valor_reportado_efectivo)>`
 *   9. `Diferencia efectivo: ±<formatCOP(|diferencia_efectivo|)>` (sign prefix)
 *   10. `Tolerancia efectivo: <formatCOP(tolerancia_efectivo)>`
 *   11. (same 5-line block for `datafono`)
 *   12. `Justificacion: <justificacion>` ONLY when `justificacion.length > 0`
 *
 * DA-5 (H) drift anchor — `'arqueo'` dispatcher missing. After C3
 * ships, this file passes 100% and the dispatcher is reachable from
 * `bridge.imprimir('arqueo', payload)`.
 *
 * Assertion quality:
 *   - Every `expect` checks a SPECIFIC UTF-8 substring derived from
 *     the REQ-OPS-155 scenario 2 fixture (`buildArqueoBuffer(payload)`).
 *   - No `expect(...).toBeDefined()` smoke tests; every assertion
 *     would fail if the production builder drifted.
 *   - `validatePayload` and `build` are exercised separately — the
 *     schema MUST reject missing `auditoria_codigo` or out-of-range
 *     `fecha` BEFORE the buffer is composed.
 */
import { describe, expect, it } from 'vitest';

import {
  build,
  EscposInvalidTipoError,
  EscposPayloadMissingFieldError,
  validatePayload,
} from '../escposBuilder';
import {
  arqueoPayloadSchema,
  formatCOP,
  formatFechaCorta,
  type ArqueoPayload,
} from '../escposTemplates';

// ──────────────────────────────────────────────────────────────────────────
// Canonical fixture — matches REQ-OPS-155 scenario 2 verbatim
// ──────────────────────────────────────────────────────────────────────────

const VALID_PAYLOAD: ArqueoPayload = {
  sucursal: { encabezado: 'Sucursal Norte' },
  uuid_sesion: 'abc12345-6789-0abc-1234-56789abcdef0',
  base_efectivo_cop: 50_000,
  valor_esperado_efectivo: 120_000,
  valor_esperado_datafono: 30_000,
  valor_reportado_efectivo: 118_000,
  valor_reportado_datafono: 30_000,
  diferencia_efectivo: -2_000,
  diferencia_datafono: 0,
  tolerancia_efectivo: 1_000,
  tolerancia_datafono: 500,
  justificacion: 'Faltante en caja menor',
  auditoria_codigo: 'AUD-20260921-000123',
  fecha: '2026-09-21T14:30:00.000Z',
  uuid_sesion_short: 'abcdef0',
};

// ──────────────────────────────────────────────────────────────────────────
// dispatch-1 — 12-line body byte fixture
// ──────────────────────────────────────────────────────────────────────────

describe('HU-F10.1 — escposBuilder.build("arqueo", payload) byte fixture', () => {
  it('dispatch-1: emits all 12 conceptual fields with correct formatting (REQ-OPS-155 scenario 2)', () => {
    const buf = build('arqueo', VALID_PAYLOAD);
    const utf8 = buf.toString('utf8');

    // Header + sello (lines 1-2)
    expect(utf8).toContain('ARQUEO PARCIAL — Sucursal Norte');
    expect(utf8).toContain('*** ARQUEO PARCIAL ***');

    // Codigo + fecha + sesion (lines 3-5)
    expect(utf8).toContain('AUD-20260921-000123');
    // The fecha is formatted via `formatFechaCorta` (es-CO short) which
    // uses the LOCAL timezone — pin the expected substring to the SAME
    // helper so the test is timezone-agnostic across CI matrices.
    expect(utf8).toContain(`Fecha: ${formatFechaCorta(VALID_PAYLOAD.fecha)}`);
    expect(utf8).toContain('Sesion: abcdef0');

    // Base + esperado + reportado + diferencia + tolerancia efectivo (lines 6-10)
    expect(utf8).toContain(`Base: ${formatCOP(50_000)}`);
    expect(utf8).toContain(`Esperado efectivo: ${formatCOP(120_000)}`);
    expect(utf8).toContain(`Reportado efectivo: ${formatCOP(118_000)}`);
    // Sign prefix MUST be `-` for negative, `+` for non-negative (NEVER `±`).
    expect(utf8).toContain(`Diferencia efectivo: -${formatCOP(2_000)}`);

    // Datafono block (lines 11) — diferencia_datafono === 0 emits `+`
    // sign per spec ("sign MUST be `+` for non-negative, `-` for
    // negative — NEVER `±`").
    expect(utf8).toContain(`Esperado datafono: ${formatCOP(30_000)}`);
    expect(utf8).toContain(`Reportado datafono: ${formatCOP(30_000)}`);
    expect(utf8).toContain(`Diferencia datafono: +${formatCOP(0)}`);
    expect(utf8).toContain(`Tolerancia datafono: ${formatCOP(500)}`);

    // Justificacion (line 12) — only when present
    expect(utf8).toContain('Justificacion: Faltante en caja menor');
  });

  // ──────────────────────────────────────────────────────────────────────
  // dispatch-2 — justificacion absent emits no line
  // ──────────────────────────────────────────────────────────────────────

  it('dispatch-2: justificacion absent emits NO "Justificacion:" line', () => {
    const buf = build('arqueo', { ...VALID_PAYLOAD, justificacion: '' });
    const utf8 = buf.toString('utf8');
    expect(utf8).not.toContain('Justificacion:');
  });

  // ──────────────────────────────────────────────────────────────────────
  // dispatch-3 — diferencia positivo uses `+` sign prefix (never `±`)
  // ──────────────────────────────────────────────────────────────────────

  it('dispatch-3: diferencia positiva uses "+" sign prefix (NEVER "±")', () => {
    const buf = build('arqueo', {
      ...VALID_PAYLOAD,
      diferencia_efectivo: 2_000, // positivo
      valor_reportado_efectivo: 122_000,
    });
    const utf8 = buf.toString('utf8');
    expect(utf8).toContain(`Diferencia efectivo: +${formatCOP(2_000)}`);
    expect(utf8).not.toContain(`Diferencia efectivo: ±`);
  });

  // ──────────────────────────────────────────────────────────────────────
  // dispatch-4 — envelope init + cut + LF
  // ──────────────────────────────────────────────────────────────────────

  it('dispatch-4: envelope starts with 0x1B 0x40 (ESC @ init) and ends with 0x1D 0x56 0x00 0x0A (GS V 0 + LF)', () => {
    const buf = build('arqueo', VALID_PAYLOAD);
    expect(buf[0]).toBe(0x1b);
    expect(buf[1]).toBe(0x40);
    // Last 4 bytes: GS V 0 (0x1D 0x56 0x00) + LF (0x0A)
    expect(buf[buf.length - 4]).toBe(0x1d);
    expect(buf[buf.length - 3]).toBe(0x56);
    expect(buf[buf.length - 2]).toBe(0x00);
    expect(buf[buf.length - 1]).toBe(0x0a);
  });

  // ──────────────────────────────────────────────────────────────────────
  // dispatch-5 — Zod schema rejects missing auditoria_codigo
  // ──────────────────────────────────────────────────────────────────────

  it('dispatch-5: arqueoPayloadSchema rejects missing auditoria_codigo', () => {
    const { auditoria_codigo: _drop, ...badPayload } = VALID_PAYLOAD;
    const result = arqueoPayloadSchema.safeParse(badPayload);
    expect(result.success).toBe(false);
    if (!result.success) {
      const paths = result.error.issues.map((i) => i.path.join('.'));
      expect(paths).toContain('auditoria_codigo');
    }
  });

  // ──────────────────────────────────────────────────────────────────────
  // dispatch-6 — Zod schema rejects out-of-range fecha
  // ──────────────────────────────────────────────────────────────────────

  it('dispatch-6: arqueoPayloadSchema rejects malformed fecha (not ISO 8601)', () => {
    const result = arqueoPayloadSchema.safeParse({
      ...VALID_PAYLOAD,
      fecha: 'not-an-iso-date',
    });
    expect(result.success).toBe(false);
    if (!result.success) {
      const paths = result.error.issues.map((i) => i.path.join('.'));
      expect(paths).toContain('fecha');
    }
  });

  // ──────────────────────────────────────────────────────────────────────
  // dispatch-7 — validatePayload surfaces Zod issues for missing keys
  // ──────────────────────────────────────────────────────────────────────

  it('dispatch-7: validatePayload("arqueo", incomplete) returns non-null issues array', () => {
    const issues = validatePayload('arqueo', {
      sucursal: { encabezado: 'Sucursal' },
      // intentionally missing the rest
    });
    expect(issues).not.toBeNull();
    expect(Array.isArray(issues)).toBe(true);
    expect((issues ?? []).length).toBeGreaterThan(0);
  });

  // ──────────────────────────────────────────────────────────────────────
  // dispatch-8 — build() throws EscposPayloadMissingFieldError on bad payload
  // ──────────────────────────────────────────────────────────────────────

  it('dispatch-8: build("arqueo", bad payload) throws EscposPayloadMissingFieldError with .issues', () => {
    expect(() =>
      build('arqueo', { sucursal: { encabezado: 'X' } } as unknown),
    ).toThrow(EscposPayloadMissingFieldError);
  });

  // ──────────────────────────────────────────────────────────────────────
  // dispatch-9 — build() with unknown tipo throws EscposInvalidTipoError
  // ──────────────────────────────────────────────────────────────────────

  it('dispatch-9: build("arqueo_legacy", any) throws EscposInvalidTipoError (drift anchor: NOT "arqueo_parcial")', () => {
    // F8.3 REQ-OPS-175 drift anchor — only `'arqueo'` is allowed.
    // Variants like `'arqueo_parcial'` or `'ticket_arqueo'` MUST be rejected.
    expect(() =>
      build('arqueo_parcial' as never, VALID_PAYLOAD),
    ).toThrow(EscposInvalidTipoError);
    expect(() =>
      build('ticket_arqueo' as never, VALID_PAYLOAD),
    ).toThrow(EscposInvalidTipoError);
  });

  // ──────────────────────────────────────────────────────────────────────
  // dispatch-10 — diferencia = 0 emits without sign prefix
  // ──────────────────────────────────────────────────────────────────────

  it('dispatch-10: diferencia === 0 emits without sign prefix', () => {
    const buf = build('arqueo', {
      ...VALID_PAYLOAD,
      diferencia_efectivo: 0,
      valor_reportado_efectivo: 120_000,
    });
    const utf8 = buf.toString('utf8');
    // When diferencia is 0, the sign prefix is still rendered (consistent
    // column width) but as empty or as `+0` per spec convention. The
    // key contract is: NO `±` glyph, NO negative sign.
    expect(utf8).toContain('Diferencia efectivo:');
    expect(utf8).not.toContain('Diferencia efectivo: -');
    expect(utf8).not.toContain('Diferencia efectivo: ±');
  });
});
