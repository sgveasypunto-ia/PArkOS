/**
 * `tarifaAgrupada.ts` — Type + helper that flattens the four
 * ``tarifas_sucursal`` rows (one per modalidad) into a single
 * row per (sucursal, tipo_vehiculo) for table rendering.
 *
 * The backend stores tarifas as 4 separate rows per (sucursal,
 * tipo_vehiculo) — one per modalidad (hora, fraccion, plena,
 * nocturna). The admin list should show ONE row per
 * (sucursal, tipo_vehiculo) with one column per modalidad, so the
 * ``ListContent`` flattens the rows on read.
 *
 * CREATE / EDIT / HISTORIAL still operate on individual rows via
 * the tarifa cell-key (sucursal, tipo_vehiculo, tipo_tarifa). The
 * admin UI splits a single form submit into 4 POSTs (one per
 * modalidad) — see ``Tarifas.tsx::onSubmit``.
 */
import type { Tarifa } from './tarifaSchema';

export interface TarifaAgrupada {
  /** Common to all 4 modalities: the cell-key minus tipo_tarifa. */
  uuid_sucursal: string;
  uuid_tipo_vehiculo: string;
  vigente_desde: string;
  vigente_hasta: string | null;
  estado: string;
  created_at: string;

  /** Per-modalidad values + the uuid of the row that carries them.
   * Used by EDIT to PUT each row individually. */
  hora: { uuid: string; valor: string | null; valor_plena: string | null };
  fraccion: { uuid: string; valor: string | null; valor_plena: string | null };
  plena: { uuid: string; valor: string | null; valor_plena: string | null };
  nocturna: {
    uuid: string;
    valor: string | null;
    valor_plena: string | null;
  };
}

/** UUIDs for the 4 canonical modalidades (HARDCODED mirror of
 * ``prod.tipo_tarifa`` from the backend — see ``Tarifas.tsx::onSubmit``
 * for the same constants). Used to lookup the per-modalidad row. */
const TIPO_TARIFA_HORA = '12e3886a-7059-47ee-bdb2-aa5fb1272bea';
const TIPO_TARIFA_FRACCION = 'c41b6602-f7b2-437d-bcfc-0462cd385eda';
const TIPO_TARIFA_PLENA = 'd83ebff8-9546-43b3-91b1-bedffa57717f';
const TIPO_TARIFA_NOCTURNA = '9f8ba4a9-6fd9-4da7-8ddb-97ce323a8600';

/**
 * Group the 4 ``tarifas_sucursal`` rows into one ``TarifaAgrupada``
 * per (sucursal, tipo_vehiculo, vigente_desde) — we keep
 * ``vigente_desde`` in the key so a future close+insert that
 * opens a new window at a new instant naturally groups the new
 * 4 rows into a new ``TarifaAgrupada`` and leaves the old 4 as a
 * separate group in history.
 *
 * Tipos sin tarifa show up as a group with all-null values and
 * only the cell-key fields populated — the list renders an "—"
 * cell for the missing modalities.
 */
export function agruparTarifas(rows: Tarifa[]): TarifaAgrupada[] {
  const map = new Map<string, TarifaAgrupada>();

  for (const r of rows) {
    const key = `${r.uuid_sucursal ?? ''}|${r.uuid_tipo_vehiculo ?? ''}|${r.vigente_desde}`;
    let entry = map.get(key);
    if (!entry) {
      entry = {
        uuid_sucursal: r.uuid_sucursal ?? '',
        uuid_tipo_vehiculo: r.uuid_tipo_vehiculo ?? '',
        vigente_desde: r.vigente_desde,
        vigente_hasta: r.vigente_hasta,
        estado: r.estado,
        created_at: r.created_at,
        hora: { uuid: '', valor: null, valor_plena: null },
        fraccion: { uuid: '', valor: null, valor_plena: null },
        plena: { uuid: '', valor: null, valor_plena: null },
        nocturna: { uuid: '', valor: null, valor_plena: null },
      };
      map.set(key, entry);
    }

    const cell = {
      uuid: r.uuid,
      valor: r.valor,
      valor_plena: r.valor_plena,
    };
    switch (r.uuid_tipo_tarifa) {
      case TIPO_TARIFA_HORA:
        entry.hora = cell;
        break;
      case TIPO_TARIFA_FRACCION:
        entry.fraccion = cell;
        break;
      case TIPO_TARIFA_PLENA:
        entry.plena = cell;
        break;
      case TIPO_TARIFA_NOCTURNA:
        entry.nocturna = cell;
        break;
      default:
        // Unknown modalidad — leave as null. The list will render
        // a dash in the corresponding cell.
        break;
    }
  }

  return Array.from(map.values());
}

/** Lookup the per-modalidad UUIDs (mirror of the backend
 * ``prod.tipo_tarifa`` table). Used by EDIT to identify which row
 * to PUT when the operator submits the modal. */
export const TIPO_TARIFA_UUIDS = {
  hora: TIPO_TARIFA_HORA,
  fraccion: TIPO_TARIFA_FRACCION,
  plena: TIPO_TARIFA_PLENA,
  nocturna: TIPO_TARIFA_NOCTURNA,
} as const;