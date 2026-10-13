/**
 * `constants.ts` — Alertas panel constants (HU-F11.2, REQ-OPS-182).
 *
 * `BUSINESS_ALERT_CODES` — the business alerts surfaced in the
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
import { severityToSeveridad, type Severidad } from '../../lib/alertas/severity';

export const BUSINESS_ALERT_CODES: ReadonlySet<string> = new Set<string>([
  'descuadre_critico',
  'fe_error_toppoint',
  'numeracion_toppoint_agotada',
  'cache_desactualizado',
  'capacidad_agotada_forzado',
  'suscripcion_proxima_vencer',
  // Emitted by the backend after PT-2 / the always-on electronic invoice.
  'fe_emision_fallida',
  'suscripcion_placa_agregada',
  'suscripcion_placa_quitada',
]);

/**
 * Operator-facing label per business code. Used when `alert-types` does not
 * carry a row for the code yet (new codes) so the alert is never dropped nor
 * shown as a raw identifier.
 *
 * Severidad por codigo = mapeo REAL del backend (`prod.alert_types.severity`
 * via `repo/alert_types.py`: critical -> alta, warning -> media, info -> baja),
 * sembrado en las migraciones 0031/0025/0032. Etiqueta/descripcion = claves
 * i18n `alertas:tipo.*` / `alertas:desc.*`. Cada codigo de negocio tiene fila
 * en el backend; los 5 codigos huerfanos que nunca tuvieron emisor ni fila en
 * `alert_types` (arqueo_sin_cerrar, caja_sin_apertura, reimpresion_excesiva,
 * fallo_conexion_local, diferencia_datafono) se retiraron.
 */
export const ALERT_CODE_FALLBACK: Readonly<
  Record<string, { severidad: Severidad; etiqueta: string; descripcion: string }>
> = {
  descuadre_critico: {
    severidad: severityToSeveridad('critical'),
    etiqueta: 'Descuadre crítico',
    descripcion: 'El arqueo cerró con descuadre mayor al umbral autorizado.',
  },
  fe_error_toppoint: {
    severidad: severityToSeveridad('critical'),
    etiqueta: 'Error de factura electrónica',
    descripcion: 'TopPoint rechazó el comprobante; revisar el motivo en la factura.',
  },
  numeracion_toppoint_agotada: {
    severidad: severityToSeveridad('critical'),
    etiqueta: 'Numeración de facturación agotada',
    descripcion: 'La resolución de facturación está por agotarse; solicitar una nueva.',
  },
  cache_desactualizado: {
    severidad: severityToSeveridad('info'),
    etiqueta: 'Caché desactualizado',
    descripcion: 'El caché local quedó desactualizado; reintentar la sincronización.',
  },
  capacidad_agotada_forzado: {
    severidad: severityToSeveridad('warning'),
    etiqueta: 'Ingreso forzado sin capacidad',
    descripcion: 'Se forzó el ingreso pese a capacidad agotada; revisar la operación.',
  },
  suscripcion_proxima_vencer: {
    severidad: severityToSeveridad('warning'),
    etiqueta: 'Suscripción próxima a vencer',
    descripcion: 'Una suscripción está próxima a vencer; contactar al cliente.',
  },
  fe_emision_fallida: {
    severidad: severityToSeveridad('warning'),
    etiqueta: 'Factura electrónica no emitida',
    descripcion:
      'No se pudo emitir una factura electrónica tras varios reintentos. El cobro quedó registrado; revisá la resolución de facturación o reintentá desde la factura.',
  },
  suscripcion_placa_agregada: {
    severidad: severityToSeveridad('info'),
    etiqueta: 'Placa agregada a una suscripción',
    descripcion: 'Un supervisor agregó una placa a una suscripción.',
  },
  suscripcion_placa_quitada: {
    severidad: severityToSeveridad('info'),
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
