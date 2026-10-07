/**
 * `constants.ts` — Alertas panel constants (HU-F11.2, REQ-OPS-182).
 *
 * `BUSINESS_ALERT_CODES` — the 11 business alerts surfaced in the
 * `<AlertasPanel />` for the operator. These are the rows that the
 * operator can act on (mark revisada, drill into the source object).
 *
 * `TECHNICAL_ALERT_CODES` — the 8 technical alerts that are SILENTLY
 * dropped per ABIERTO-06. They belong to a different audience (the
 * cloud-side `JobSyncCloud` operator surfaces them in Grafana); the
 * FE is the authority boundary for the 8-vs-11 filter.
 *
 * Drift anchor DA-F11.2-5: adding a 12th business alert is a
 * one-line change here — the hook filters via `Set.has(...)` so
 * there is no enumeration loop anywhere else.
 */
export const BUSINESS_ALERT_CODES: ReadonlySet<string> = new Set<string>([
  'descuadre_critico',
  'fe_error_toppoint',
  'numeracion_toppoint_agotada',
  'cache_desactualizado',
  'capacidad_agotada_forzado',
  'arqueo_sin_cerrar',
  'caja_sin_apertura',
  'suscripcion_proxima_vencer',
  'reimpresion_excesiva',
  'fallo_conexion_local',
  'diferencia_datafono',
  // Emitted by the backend after PT-2 / the always-on electronic invoice.
  'fe_emision_fallida',
  'suscripcion_placa_agregada',
  'suscripcion_placa_quitada',
]);

/**
 * Operator-facing label per business code. Used when `alert-types` does not
 * carry a row for the code yet (new codes) so the alert is never dropped nor
 * shown as a raw identifier.
 */
export const ALERT_CODE_FALLBACK: Readonly<
  Record<string, { severidad: 'alta' | 'media' | 'baja'; etiqueta: string; descripcion: string }>
> = {
  fe_emision_fallida: {
    severidad: 'media',
    etiqueta: 'Factura electrónica no emitida',
    descripcion:
      'No se pudo emitir una factura electrónica tras varios reintentos. El cobro quedó registrado; revisá la resolución de facturación o reintentá desde la factura.',
  },
  suscripcion_placa_agregada: {
    severidad: 'baja',
    etiqueta: 'Placa agregada a una suscripción',
    descripcion: 'Un supervisor agregó una placa a una suscripción.',
  },
  suscripcion_placa_quitada: {
    severidad: 'baja',
    etiqueta: 'Placa quitada de una suscripción',
    descripcion: 'Un supervisor quitó una placa de una suscripción.',
  },
};

export const TECHNICAL_ALERT_CODES: ReadonlySet<string> = new Set<string>([
  'hash_chain_anomaly',
  'dian_rechazada',
  'dian_timeout',
  'dian_error',
  'branch_offline_reauth_required',
  'orphan_workflow_chain',
  'fe_provider_error',
  'fe_numbering_exhausted',
]);

/**
 * `isBusinessAlert` — `Set.has(...)` (O(1)) per REQ-OPS-182
 * perf-sanity scenario.
 */
export function isBusinessAlert(tipo_alerta: string | null | undefined): boolean {
  if (!tipo_alerta) return false;
  return BUSINESS_ALERT_CODES.has(tipo_alerta);
}

/**
 * `isTechnicalAlert` — `Set.has(...)` per REQ-OPS-182. Note that
 * `isBusinessAlert` is the authority boundary; an alert whose
 * `tipo_alerta` is neither business NOR technical is treated as
 * unknown and dropped silently per ABIERTO-06.
 */
export function isTechnicalAlert(tipo_alerta: string | null | undefined): boolean {
  if (!tipo_alerta) return false;
  return TECHNICAL_ALERT_CODES.has(tipo_alerta);
}
