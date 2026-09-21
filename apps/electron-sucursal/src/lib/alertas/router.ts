/**
 * `router.ts` — per-`tipo_alerta` drill-down router map (HU-F11.2,
 * REQ-OPS-178 + DA-F11.2-4).
 *
 * Each business `tipo_alerta` resolves to a route target. The
 * resolver reads from the alert row:
 *   - `descuadre_critico` → `/caja/arqueo/{uuid_arqueo}`
 *   - `fe_error_toppoint` → `/facturacion/fe/{uuid}`
 *   - `numeracion_toppoint_agotada` → `/admin/resoluciones`
 *   - `cache_desactualizado` → `/sync/detalle`
 *   - `capacidad_agotada_forzado` → `/caja/ingreso/{datos_nuevos.uuid_ingreso}`
 *     (DA-F11.2-14 — JSONB column drill-down)
 *   - Other 6 business codes → `/alertas/{alert.uuid}` (default detail)
 *
 * If a code lacks the FK field, the function returns the default
 * `/alertas/{alert.uuid}` route — the panel renders gracefully even
 * for partially hydrated rows.
 */
import type { MergedAlerta } from '../api/schemas/alertas';

export type DrillDownFn = (alert: MergedAlerta) => string;

const DEFAULT_DRILL_DOWN: DrillDownFn = (alert) => `/alertas/${alert.uuid}`;

export const DRILL_DOWN_ROUTES: Readonly<Record<string, DrillDownFn>> = {
  descuadre_critico: (alert) => (alert.uuid_arqueo ? `/caja/arqueo/${alert.uuid_arqueo}` : DEFAULT_DRILL_DOWN(alert)),
  fe_error_toppoint: (alert) => `/facturacion/fe/${alert.uuid}`,
  numeracion_toppoint_agotada: () => '/admin/resoluciones',
  cache_desactualizado: () => '/sync/detalle',
  capacidad_agotada_forzado: (alert) => {
    const dn = alert.datos_nuevos as Record<string, unknown> | null | undefined;
    const uuid_ingreso = dn && typeof dn.uuid_ingreso === 'string' ? dn.uuid_ingreso : null;
    return uuid_ingreso ? `/caja/ingreso/${uuid_ingreso}` : DEFAULT_DRILL_DOWN(alert);
  },
  arqueo_sin_cerrar: (alert) => (alert.uuid_arqueo ? `/caja/arqueo/${alert.uuid_arqueo}` : DEFAULT_DRILL_DOWN(alert)),
  caja_sin_apertura: () => '/caja/abrir-turno',
  suscripcion_proxima_vencer: () => '/suscripciones',
  reimpresion_excesiva: () => '/facturacion/reimprimir',
  fallo_conexion_local: () => '/sync/detalle',
  diferencia_datafono: (alert) => (alert.uuid_arqueo ? `/caja/arqueo/${alert.uuid_arqueo}` : DEFAULT_DRILL_DOWN(alert)),
};

/**
 * `drillDownHref` — pure selector: returns the route for `alert.tipo_alerta`
 * or the default `/alertas/{uuid}` fallback. The router map is the
 * single source of truth for per-`tipo_alerta` drill-down.
 */
export function drillDownHref(alert: MergedAlerta): string {
  const code = alert.tipo_alerta;
  if (!code) return DEFAULT_DRILL_DOWN(alert);
  const fn = DRILL_DOWN_ROUTES[code];
  return fn ? fn(alert) : DEFAULT_DRILL_DOWN(alert);
}
