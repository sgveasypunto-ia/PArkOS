/**
 * `estadoFactura.ts` — minimal MVP derivation of `prod.facturas.estado`
 * for the drill-down header card.
 *
 * REQ-X-02 mandates that the header shows an `estado` badge. The canonical
 * source is the `V_FACTURA_ESTADO` view in the BE (DERV-1 in the data
 * model), but no HTTP endpoint currently exposes it directly — only the
 * `GET /admin/reporteria/facturas` flat list returns it (as `estado:
 * 'vigente' | 'anulada'`). The drill-down's BE endpoint
 * `GET /facturacion/facturas/{uuid}` (plural, factory) returns the raw
 * row without the `estado` column.
 *
 * The MVP heuristic: if the `prod.log_transaccional` last action for
 * this factura is `anular` (workflow `anulaciones`, REQ-OPS-201), state
 * is `anulada`; otherwise `vigente`. When the BE exposes
 * `V_FACTURA_ESTADO` as a real endpoint (future HU), this shim is
 * removed.
 *
 * The function is pure and synchronous — no fetch, no async. The caller
 * (the SWR `hash` data) supplies the log row.
 */
import type { LogTransaccionalItem } from '../api/facturacionAdminSchema';

export type FacturaEstado = 'vigente' | 'anulada';

export const FACTURA_ESTADOS: readonly FacturaEstado[] = ['vigente', 'anulada'];

/**
 * `deriveEstadoFactura(items)` — given the log_transaccional items for
 * a factura (last-action semantics: caller MUST pass them sorted by
 * `timestamp_evento` DESC, or just the first matching one is enough),
 * return the derived estado.
 *
 * Heuristic: if any item has `accion === 'anular'` AND
 * `tabla_afectada === 'anulaciones'`, the factura was voided.
 *
 * NOTE: this is a coarse MVP shim. The canonical source is
 * `prod.V_FACTURA_ESTADO` (HU-F1.9 design, DERV-1) — when a BE endpoint
 * exposes it, swap this for a `fetchEstadoFactura(uuid)` call.
 */
export function deriveEstadoFactura(
  items: readonly LogTransaccionalItem[],
): FacturaEstado {
  if (items.length === 0) return 'vigente';
  // Items come in DESC order from the BE (cursor pagination newest-first).
  // The most recent action on this factura wins.
  const head = items[0];
  if (head.accion === 'anular' && head.tabla_afectada === 'anulaciones') {
    return 'anulada';
  }
  return 'vigente';
}
