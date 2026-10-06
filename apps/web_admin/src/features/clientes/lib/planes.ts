/**
 * Compatibilidad plan <-> tipo de vehículo (PT-2): un plan con
 * `uuid_tipo_vehiculo` solo admite vehículos de ese tipo; un plan sin tipo
 * (NULL) admite cualquiera. Espejo de la regla del backend
 * (`tipo_vehiculo_plan_incompatible`), usado para filtrar el selector y
 * validar antes de enviar.
 */

export interface PlanConTipo {
  uuid: string;
  uuid_tipo_vehiculo?: unknown;
}

function planTipo(plan: PlanConTipo): string | null {
  const t = plan.uuid_tipo_vehiculo;
  return typeof t === 'string' && t !== '' ? t : null;
}

/** Distinct, non-empty vehicle-type uuids from a list (unknown/null types are skipped). */
export function tiposDistintos(tipos: ReadonlyArray<string | null | undefined>): string[] {
  return [...new Set(tipos.filter((t): t is string => typeof t === 'string' && t !== ''))];
}

/** True when every given vehicle type is accepted by the plan. */
export function planAceptaTipos(plan: PlanConTipo, tipos: ReadonlyArray<string>): boolean {
  const tipoPlan = planTipo(plan);
  if (tipoPlan === null) return true;
  return tipos.every((t) => t === tipoPlan);
}

/** Plans compatible with the selected vehicles' types (all plans when none selected). */
export function planesCompatibles<P extends PlanConTipo>(
  planes: ReadonlyArray<P>,
  tipos: ReadonlyArray<string>,
): P[] {
  return planes.filter((p) => planAceptaTipos(p, tipos));
}
