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
 */
import { z } from 'zod';

export const MiTurnoSchema = z
  .object({
    uuid_sesion: z.string().uuid(),
    uuid_sucursal: z.string().uuid(),
    timestamp_calculo: z.string(),
    ingresos_count: z.number().int().nonnegative(),
    salidas_count: z.number().int().nonnegative(),
    total_cobrado_efectivo_cop: z.number().nonnegative(),
    total_cobrado_datafono_cop: z.number().nonnegative(),
  })
  .strict();

export type MiTurnoReadWire = z.infer<typeof MiTurnoSchema>;