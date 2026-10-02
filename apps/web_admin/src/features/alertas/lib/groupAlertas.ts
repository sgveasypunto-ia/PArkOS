/**
 * `groupAlertas.ts` -- BR3 (plan.md HU-F19.5): VISUAL grouping by
 * `(tipo_alerta, uuid_sucursal, día)` for the alertas inbox.
 *
 * This is presentation-only, over the SAME rows the container already
 * fetched -- it never drops, filters, or reorders data out of the
 * dataset. `buildAlertaGroups` returns every input row, partitioned into
 * groups in first-seen order; the caller (`AlertasTable`) decides how to
 * render each group (a lone-item group renders as a plain row, a
 * multi-item group renders as a collapsed-by-default, expandable header
 * with a count badge -- see that component for the UI side of BR3).
 */
import type { AlertaRead } from '../api/alertasSchema';

export interface AlertaGroup {
  /** Stable key: `${tipo_alerta}|${uuid_sucursal}|${dia}`. */
  key: string;
  tipoAlerta: string;
  uuidSucursal: string;
  dia: string;
  items: AlertaRead[];
}

/** `YYYY-MM-DD` from `timestamp_evento`, falling back to `created_at`. */
export function diaOf(item: AlertaRead): string {
  const source = item.timestamp_evento ?? item.created_at;
  return source.slice(0, 10);
}

function keyOf(item: AlertaRead): { key: string; tipoAlerta: string; uuidSucursal: string; dia: string } {
  const tipoAlerta = item.tipo_alerta ?? '';
  const uuidSucursal = item.uuid_sucursal ?? '';
  const dia = diaOf(item);
  return { key: `${tipoAlerta}|${uuidSucursal}|${dia}`, tipoAlerta, uuidSucursal, dia };
}

/**
 * Partitions `items` into groups by `(tipo_alerta, uuid_sucursal, día)`,
 * preserving first-seen order for both the groups themselves and the
 * rows within each group. Every input row appears in exactly one output
 * group -- `items.flatMap(g => g.items)` reproduces the original array.
 */
export function buildAlertaGroups(items: readonly AlertaRead[]): AlertaGroup[] {
  const order: string[] = [];
  const groups = new Map<string, AlertaGroup>();

  for (const item of items) {
    const { key, tipoAlerta, uuidSucursal, dia } = keyOf(item);
    let group = groups.get(key);
    if (!group) {
      group = { key, tipoAlerta, uuidSucursal, dia, items: [] };
      groups.set(key, group);
      order.push(key);
    }
    group.items.push(item);
  }

  return order.map((key) => groups.get(key)!);
}
