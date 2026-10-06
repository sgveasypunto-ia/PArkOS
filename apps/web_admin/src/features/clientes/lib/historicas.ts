/**
 * "Históricas" = closed/inactive versions only. The `/history` endpoint also
 * returns the OPEN row of each vigente subscription (history is looked up by
 * the vigente's own uuid), which used to show the same subscription twice
 * (once under "Vigentes" with "vence en N días", once under "Históricas" with
 * estado `activo`). Expired-but-still-open rows stay in "Vigentes" (flagged
 * "vencida hace N días"; they are the ones that can be renewed).
 */
import type { SubscripcionCliente } from '../api/clientesApi';

export function soloHistoricas(
  candidatas: SubscripcionCliente[],
  vigentes: SubscripcionCliente[],
): SubscripcionCliente[] {
  const vigentesUuids = new Set(vigentes.map((s) => s.uuid));
  const vistas = new Set<string>();
  return candidatas.filter((s) => {
    if (vigentesUuids.has(s.uuid) || vistas.has(s.uuid)) return false;
    if (s.vigente_hasta === null && s.estado === 'activo') return false;
    vistas.add(s.uuid);
    return true;
  });
}
