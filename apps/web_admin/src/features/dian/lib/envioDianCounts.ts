/**
 * `envioDianCounts.ts` — best-effort per-`estado` counters for the
 * HU-F20.5 "monitor de envíos DIAN" resumen section.
 *
 * Unlike HU-F19.1/F19.2's sync resumen (`sync_estado_agregado`, a
 * DEDICATED backend aggregate endpoint over the full dataset), there is
 * no equivalent aggregate endpoint for `envio_dian` — only the raw
 * cursor-paginated `GET /api/v1/envio-dian` listing. Adding one is out
 * of scope for this FE-only slice (the task brief explicitly scopes
 * "no new backend endpoints unless strictly indispensable", and a
 * resumen is a nice-to-have, not indispensable).
 *
 * So these counts are deliberately a BEST-EFFORT window: whatever is
 * currently loaded (the most recent page(s) of the UNFILTERED listing),
 * never a true cross-dataset total. `<DianCola />` labels the resumen
 * accordingly so it never implies a precision it doesn't have.
 */
import type { EnvioDianEstado, EnvioDianRead } from '../api/envioDianSchema';
import { ENVIO_DIAN_ESTADOS } from '../api/envioDianSchema';
import { normalizeEnvioDianEstado } from './envioDianEstado';

export type EnvioDianCounts = Record<EnvioDianEstado, number>;

function emptyCounts(): EnvioDianCounts {
  const counts = {} as EnvioDianCounts;
  for (const estado of ENVIO_DIAN_ESTADOS) counts[estado] = 0;
  return counts;
}

/**
 * Tallies `items` by `estado`, ignoring rows whose `estado` is `null` or
 * outside the known domain (defensive -- `EnvioDianRead.estado` is
 * modeled as a free-form nullable string, see `envioDianSchema.ts`).
 */
export function buildEnvioDianCounts(items: readonly EnvioDianRead[]): EnvioDianCounts {
  const counts = emptyCounts();
  for (const item of items) {
    // 'activo' (a dispatch in flight) counts as en_proceso.
    const estado = normalizeEnvioDianEstado(item.estado);
    if (estado !== null) counts[estado] += 1;
  }
  return counts;
}
