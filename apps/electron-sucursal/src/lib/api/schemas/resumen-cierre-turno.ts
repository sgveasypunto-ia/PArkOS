/**
 * `ResumenCierreTurnoSchema` — Zod mirror of BE Pydantic
 * `ResumenCierreTurnoRead` (`GET /operacion/mi-turno/resumen-cierre`).
 *
 * Additive sibling of `MiTurnoSchema` (which stays frozen at 7 fields).
 * `.strict()` so BE drift fails loudly; `Decimal` fields travel as JSON
 * strings, hence `z.coerce.number()`.
 *
 * BE counterpart: `backend/tests/integration/test_resumen_cierre_turno.py`
 * (key-set lock).
 */
import { z } from 'zod';

export const ResumenCierreMedioPagoSchema = z
  .object({
    medio_pago: z.string(),
    pagos_count: z.number().int().nonnegative(),
    total_cop: z.coerce.number(),
  })
  .strict();

export const ResumenCierreTurnoSchema = z
  .object({
    uuid_sesion: z.string().uuid(),
    uuid_sucursal: z.string().uuid(),
    timestamp_calculo: z.string(),
    ingresos_count: z.number().int().nonnegative(),
    salidas_count: z.number().int().nonnegative(),
    transacciones_count: z.number().int().nonnegative(),
    medios_pago: z.array(ResumenCierreMedioPagoSchema),
    reversos_count: z.number().int().nonnegative(),
    reversos_total_cop: z.coerce.number(),
  })
  .strict();

export type ResumenCierreMedioPago = z.infer<typeof ResumenCierreMedioPagoSchema>;
export type ResumenCierreTurnoRead = z.infer<typeof ResumenCierreTurnoSchema>;
