/**
 * `parametrizacionEfectivaApi.ts` — thin GET wrappers for the HU-F15.1 BR4
 * ``vigente_en`` bi-temporal filter.
 *
 * Endpoints consumed (all mounted on `api_admin`/`api_sucursal` per
 * `api/v1/__init__.py`, except `resolucion-facturacion` which is
 * DIAN-root / cloud-only and therefore only reachable on `api_admin`):
 *
 * - `GET /api/v1/empresa/tarifas-sucursal?vigente_en=...`
 * - `GET /api/v1/empresa/cantidad-vehiculos-sucursal?vigente_en=...`
 * - `GET /api/v1/empresa/resolucion-facturacion?vigente_en=...`
 *
 * None of the 3 list endpoints accept a server-side `uuid_sucursal` filter
 * on this dedicated path (same client-side-filter convention already used
 * by `features/tarifas/pages/Tarifas.tsx`'s `allFiltered` — see that
 * file's module docstring), so every function here filters the returned
 * `items` by `uuid_sucursal` client-side before counting/returning.
 */
import { parkosFetchRaw } from '@parkos/ui-kit/fetch';

export interface ParametrizacionEfectivaCounts {
  tarifasVigentes: number;
  capacidadVigente: number;
  resolucionesVigentes: number;
}

interface ReadListEnvelope {
  items: Array<{ uuid_sucursal: string | null }>;
  next_cursor: string | null;
}

async function countVigentes(
  path: string,
  opts: { uuidSucursal: string; vigenteEn: string },
): Promise<number> {
  const { uuidSucursal, vigenteEn } = opts;
  const params = new URLSearchParams({ vigente_en: vigenteEn, limit: '200' });
  const res = await parkosFetchRaw(`${path}?${params.toString()}`, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  if (!res.ok) {
    if (res.status === 404) return 0;
    const body = await res.text();
    throw new Error(`parametrizacionEfectivaApi: GET ${path} -> ${res.status}: ${body.slice(0, 200)}`);
  }
  const envelope = (await res.json()) as ReadListEnvelope;
  return envelope.items.filter((item) => item.uuid_sucursal === uuidSucursal).length;
}

/**
 * Resolve the 3 vigente-at-date counts for one branch in parallel.
 *
 * `resolucion-facturacion` is cloud-only (DIAN root, REQ-X3): on a branch
 * deploy the request 404s (route absent) and this function treats that
 * the same as "zero rows" rather than surfacing a hard error — the
 * Resoluciones tab is a placeholder in this HU anyway (T1), so the count
 * is informational only.
 */
export async function getParametrizacionEfectiva(
  uuidSucursal: string,
  vigenteEn: string,
): Promise<ParametrizacionEfectivaCounts> {
  const [tarifasVigentes, capacidadVigente, resolucionesVigentes] = await Promise.all([
    countVigentes('/api/v1/empresa/tarifas-sucursal', { uuidSucursal, vigenteEn }),
    countVigentes('/api/v1/empresa/cantidad-vehiculos-sucursal', { uuidSucursal, vigenteEn }),
    countVigentes('/api/v1/empresa/resolucion-facturacion', { uuidSucursal, vigenteEn }).catch(
      () => 0,
    ),
  ]);
  return { tarifasVigentes, capacidadVigente, resolucionesVigentes };
}
