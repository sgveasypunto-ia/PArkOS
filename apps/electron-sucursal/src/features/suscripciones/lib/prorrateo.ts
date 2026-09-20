/**
 * `prorrateo.ts` — pure helper that mirrors F1.12 backend
 * `repo/venta_suscripcion.py::calcular_prorrateo` (DEC-VENTA-03,
 * A-09 in plan.md:460).
 *
 * Formula (verbatim from F1.12 REQ-OPS-090 with last-day defensive
 * clamp):
 *   valor_dia = plan.valor / plan.duracion_dias
 *   dias_restantes_mes = max(1, lastDayOfMonth(fecha) - fecha.day)
 *   monto_proporcional = valor_dia * dias_restantes_mes
 *      IF fecha.day > 15 ELSE null
 *
 * The `max(1, ...)` clamp is the client-side guard for the edge
 * case where `fecha` IS the last day of the month: F1.12's literal
 * formula `(lastDay - day)` would yield 0 for `day = lastDay`,
 * charging $0 prorrateo. The clamp yields 1 day (today) for that
 * edge case, matching the operator-facing expectation in the
 * A-09 UX rule. The backend authoritative amount lives in
 * `prod.factura_detalle.valor_unitario` — this mirror is
 * informational; the 4 unit tests pin both the canonical F1.12
 * reference cases (day=20→10, day=19→11) AND the last-day edge
 * (day=30→1).
 *
 * The wizard step 4 displays "Monto prorrateado: $X" ONLY when this
 * helper returns non-null. The authoritative source remains
 * `prod.factura_detalle.valor_unitario` (A-09) — this client mirror
 * is informational. Drift between client and server breaks the
 * `prorrateo.test.ts` reference cases.
 *
 * No I/O, no async, no React: pure function, easy unit test.
 */
export interface PlanProporcionalInput {
  readonly valor: number;
  readonly duracion_dias: number;
}

/**
 * Thrown when `plan.duracion_dias <= 0`. F1.12 backend raises the
 * same condition (`PlanDuracionDiasInvalidoError`, REQ-OPS-088). The
 * client mirror throws defensively so the wizard never divides by
 * zero or computes a negative prorrateo.
 */
export class PlanDuracionDiasInvalidoError extends Error {
  constructor(public readonly duracion_dias: number) {
    super(`plan_duracion_dias_invalido: ${duracion_dias}`);
    this.name = 'PlanDuracionDiasInvalidoError';
  }
}

/**
 * `calcularMontoProporcional(plan, fecha)` — returns `null` when
 * `fecha.day <= 15` (no prorrateo per A-09 decay rule); otherwise
 * `(plan.valor / plan.duracion_dias) * (lastDayOfMonth - fecha.day)`.
 *
 * @throws {PlanDuracionDiasInvalidoError} when `plan.duracion_dias <= 0`.
 */
export function calcularMontoProporcional(
  plan: PlanProporcionalInput,
  fecha: Date,
): number | null {
  if (plan.duracion_dias <= 0) {
    throw new PlanDuracionDiasInvalidoError(plan.duracion_dias);
  }
  if (fecha.getDate() <= 15) {
    return null;
  }
  const valorDia = plan.valor / plan.duracion_dias;
  // Day 0 of the NEXT month is the last day of `fecha`'s month; jsdom
  // and modern engines handle month rollover correctly (e.g. month=11
  // + 1 → month=0 of next year, day 0 = last day of December).
  const lastDayOfMonth = new Date(fecha.getFullYear(), fecha.getMonth() + 1, 0).getDate();
  // Clamp at minimum 1: the last day of the month must yield ≥1 day
  // remaining (you never charge $0 prorrateo for a same-day sale).
  // Matches F1.12 day=20→10, day=19→11 reference cases; the clamp
  // only diverges when day = lastDay (F1.12 has no spec for that
  // case — this client mirror's defensive answer is 1).
  const diasRestantes = Math.max(1, lastDayOfMonth - fecha.getDate());
  return valorDia * diasRestantes;
}
