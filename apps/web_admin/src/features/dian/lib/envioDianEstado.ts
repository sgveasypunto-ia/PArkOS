/**
 * `normalizeEnvioDianEstado` -- maps the raw `envio_dian.estado` to the state a
 * monitor shows.
 *
 * `envio_dian` is append-only: the dispatcher never edits a row, it appends the
 * next one, and the LAST row of a chain is the state. The row a dispatch
 * registers before talking to the provider carries `estado = 'activo'` (the
 * table's bi-temporal default), which to an operator simply means "in process".
 * Showing it as a dash (unknown) hid every in-flight send and left it out of
 * the summary tiles.
 */
import type { EnvioDianEstado } from '../api/envioDianSchema';
import { ENVIO_DIAN_ESTADOS } from '../api/envioDianSchema';

export function normalizeEnvioDianEstado(estado: string | null): EnvioDianEstado | null {
  if (estado === null) return null;
  if (estado === 'activo') return 'en_proceso';
  return (ENVIO_DIAN_ESTADOS as readonly string[]).includes(estado)
    ? (estado as EnvioDianEstado)
    : null;
}
