/**
 * `MiTurnoSchema` — Zod mirror of BE Pydantic `MiTurnoRead`
 * (HU-F12.1, REQ-OPS-184 + REQ-OPS-189).
 *
 * Field-by-field parity with the backend (DA-F12.1-1 / DA-F12.1-9
 * GATING): snake_case verbatim, ``.strict()`` rejects hypothetical 8th
 * fields. Drift between BE and FE breaks CI on both pyramids:
 *   - BE: ``backend/tests/unit/test_mi_turno_schema.py``
 *   - FE: ``apps/electron-sucursal/src/lib/api/schemas/__tests__/
 *     mi-turno.test.ts``
 *
 * The schema is consumed by ``features/operacion/hooks/useMiTurno.ts``
 * (after `parkosFetch` returns the raw payload) and by the API stub
 * ``features/operacion/api/miTurnoApi.ts``.
 *
 * REGRESSION fix (2026-09-22): the two ``total_cobrado_*`` fields are
 * ``Decimal`` on the BE side. Pydantic v2 serializes Decimal as a JSON
 * STRING by default (e.g. ``"total_cobrado_efectivo_cop":"0"``); the
 * ``MiTurnoSchema`` previously declared ``z.number()`` and Zod threw
 * on the wire, which collapsed the whole payload to the all-zero
 * ``emptyMiTurno`` fallback in the panel — the operator saw 0 ingresos
 * even when 25 existed in the turn. We use ``z.coerce.number()`` on
 * the two Decimal fields so a wire-format string number parses to a
 * real number and then passes ``nonnegative()``. Test S1b locks this
 * contract. The two integer count fields stay strict ``z.number().int()``
 * because the BE sends them as JSON numbers already (no coercion needed).
 */
import { z } from 'zod';

export const MiTurnoSchema = z
  .object({
    uuid_sesion: z.string().uuid(),
    uuid_sucursal: z.string().uuid(),
    timestamp_calculo: z.string(),
    ingresos_count: z.number().int().nonnegative(),
    salidas_count: z.number().int().nonnegative(),
    total_cobrado_efectivo_cop: z.coerce.number().nonnegative(),
    total_cobrado_datafono_cop: z.coerce.number().nonnegative(),
  })
  .strict();

export type MiTurnoReadWire = z.infer<typeof MiTurnoSchema>;