/**
 * `lib/subscripciones.ts` — shared day-math helpers for subscription
 * expiry (HU-F20.1).
 *
 * NEW shared helper. A prior planning note (plan.md) assumed Fase 17
 * reportería already exposed `useProximasVencer`/`diasParaVencer` in
 * `apps/web_admin` -- verified FALSE before writing this file: there
 * were zero hits for those names anywhere under `apps/web_admin/src`.
 * The only prior art is the backend's own cohort math in
 * `backend/packages/parkos_core/src/parkos_core/api/v1/reporteria.py`
 * (`reporte_suscripciones_cohorte`, REQ-OPS-181, "próximas a vencer"
 * block around line 1281-1316) and an unrelated hook in the separate
 * `apps/electron-sucursal` app (`useRequiereJustificacion.ts`, a
 * different concern entirely). First consumer of this file:
 * `features/clientes/components/ClienteSuscripciones.tsx`.
 *
 * Day-math/ordering/exclusion semantics mirror the backend block
 * exactly (not its SQL): `dias_para_vencer = (fecha_vencimiento -
 * today).days`, rows with `dias_para_vencer < 0` (vencidas) excluded,
 * ascending by days remaining.
 */
import { useMemo } from 'react';

/**
 * Days between today and `fechaVencimiento` (ceil'd — a date-only value
 * has no fractional component, so this matches the backend's exact
 * integer-day Python `date` subtraction). `null` for a missing/invalid
 * date. Negative means already vencida; `0` means vence hoy.
 */
export function diasParaVencer(
  fechaVencimiento: string | Date | null | undefined,
): number | null {
  if (fechaVencimiento === null || fechaVencimiento === undefined) return null;

  const target =
    typeof fechaVencimiento === 'string' ? new Date(fechaVencimiento) : fechaVencimiento;
  if (Number.isNaN(target.getTime())) return null;

  const today = new Date();
  // Both sides resolved from their UTC calendar components (NOT local
  // get*/Date() accessors) -- the backend's "today" is
  // ``datetime.now(UTC).date()`` (explicitly UTC), and a date-only wire
  // value (``"2026-06-25"``, no time, no offset) is parsed by `Date` as
  // UTC midnight. Reading it back with LOCAL accessors would silently
  // shift the perceived calendar day by the host's timezone offset (a
  // real off-by-one bug caught by this file's own test suite running in
  // a non-UTC-local CI sandbox) -- UTC accessors on both sides keep the
  // comparison timezone-independent and exactly mirrors the backend's
  // plain `date` subtraction.
  const todayUTC = Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate());
  const targetUTC = Date.UTC(target.getUTCFullYear(), target.getUTCMonth(), target.getUTCDate());

  const msPerDay = 24 * 60 * 60 * 1000;
  return Math.ceil((targetUTC - todayUTC) / msPerDay);
}

/**
 * Items whose `dias_para_vencer` is in `[0, diasUmbral]` (already-vencidas
 * and anything further out excluded), sorted ascending by days remaining
 * -- mirrors REQ-OPS-181's "próximas a vencer" semantics.
 *
 * Named `use*` for call-site consistency with the rest of this codebase's
 * hooks, but it is a pure filtering function -- `useMemo` is used
 * internally purely as a perf guard against recomputing on every render
 * for the same `items`/`diasUmbral` pair (no other React-specific
 * behavior, e.g. no reactive "today" tick, is needed here).
 */
export function useProximasVencer<T extends { fecha_vencimiento?: string | Date | null }>(
  items: T[],
  diasUmbral = 30,
): T[] {
  return useMemo(() => {
    return items
      .map((item) => ({ item, dias: diasParaVencer(item.fecha_vencimiento) }))
      .filter(
        (entry): entry is { item: T; dias: number } =>
          entry.dias !== null && entry.dias >= 0 && entry.dias <= diasUmbral,
      )
      .sort((a, b) => a.dias - b.dias)
      .map((entry) => entry.item);
  }, [items, diasUmbral]);
}

/**
 * HU-F20.2 / CU-06 BR2 -- "monto de referencia del primer periodo"
 * (prorrateo), computed CLIENT-SIDE ONLY and NEVER sent to the backend as
 * a real charge (BR2: the actual cobro is a separate act, out of scope
 * for this maintenance screen). Mirrors the backend's own
 * `repo.venta_suscripcion.calcular_prorrateo` formula EXACTLY so the
 * number shown here matches what the sale/cobro flow would charge if the
 * admin later processes payment for this same subscripcion:
 *
 *   valor_dia = plan.valor / plan.duracion_dias
 *   monto_proporcional = valor_dia * dias_restantes_del_mes   (day > 15)
 *   monto_proporcional = plan.valor                            (day <= 15)
 *
 * Returns `null` when the inputs can't produce a number (missing plan
 * data, invalid date, or `duracion_dias <= 0` -- mirrors the backend's
 * own `PlanDuracionDiasInvalidoError` edge case, just returning `null`
 * instead of raising, since this is a read-only UI preview).
 */
export function calcularMontoReferencia(
  plan: { valor?: number | string | null; duracion_dias?: number | null } | null | undefined,
  fechaInicioCobertura: string | null | undefined,
): number | null {
  if (!plan || !fechaInicioCobertura) return null;
  const valor = typeof plan.valor === 'string' ? Number(plan.valor) : plan.valor;
  const duracionDias = plan.duracion_dias;
  if (valor === null || valor === undefined || Number.isNaN(valor)) return null;
  if (!duracionDias || duracionDias <= 0) return null;

  const fecha = new Date(fechaInicioCobertura);
  if (Number.isNaN(fecha.getTime())) return null;

  const day = fecha.getUTCDate();
  if (day <= 15) return Math.round(valor * 100) / 100;

  const valorDia = valor / duracionDias;
  const diasEnMes = new Date(Date.UTC(fecha.getUTCFullYear(), fecha.getUTCMonth() + 1, 0)).getUTCDate();
  const diasRestantes = diasEnMes - day;
  return Math.round(valorDia * diasRestantes * 100) / 100;
}
