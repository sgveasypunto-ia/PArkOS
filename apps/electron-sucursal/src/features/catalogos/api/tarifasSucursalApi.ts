/**
 * `tarifasSucursalApi.ts` — HTTP layer para el catálogo de tarifas vigentes
 * por sucursal (HU-F4.2 — T2, segundo consumer del feature `catalogos`).
 *
 * Backend (HU-F1.4 closed, READ ONLY):
 *   - `GET /api/v1/empresa/tarifas-sucursal?vigente_en=<iso>&cursor=...`
 *     — handler `empresa.py:179-213` (list endpoint, paginated `limit=50`).
 *   - Helper `repo/tarifas_vigencia.py::list_tarifas_vigentes` filtra por
 *     fecha bi-temporal + estado activo + uuid_sucursal del operador.
 *   - Response shape `TarifasSucursalRead` (`schemas/empresa.py:265-280`):
 *     `{ uuid, uuid_sucursal, uuid_tipo_vehiculo, uuid_tipo_tarifa, valor,
 *        valor_plena, vigente_desde, vigente_hasta, estado, created_at,
 *        created_by, sync_status }`.
 *
 * Documented refinement (HU-F1.4 AC literal vs backend handler signature):
 *   - plan.md AC describe `?uuid_tipo_vehiculo=X&vigente_en=<ahora>`.
 *   - El handler dedicado `empresa.py:179-213` SOLO expone `vigente_en`
 *     (el helper `TarifasSucursalFilter` acepta `uuid_tipo_vehiculo` pero
 *     el handler no lo wirea a la firma).
 *   - F4.2 hace client-side filter sobre `TarifasSucursalRead[]` (mismo
 *     patrón que F4.1 `useTiposVehiculo` — catálogos pequeños
 *     por sucursal, <50 rows en `limit=50`). Resultado idéntico al AC
 *     para datasets del operador. Follow-up PR puede agregar el query
 *     param al handler dedicado sin breaking change.
 *
 * DEC-F4.2-03 verbatim (404 → vacío): una sucursal sin tarifas
 * configuradas devuelve 404 del backend; el cliente retorna
 * `{items:[], next_cursor:null}` para que `useTarifasVigentes` reciba
 * un snapshot vacío válido (la primera fila se omite, `tarifa === null`,
 * el badge permanece oculto). El SWR `shouldRetryOnError` excluye 404.
 *
 * `parkosFetch` invariants (F2.2):
 *   - Bearer token desde `authStore` (auto).
 *   - 401 once-refresh via `refreshAccessToken()` Mutex.
 *   - 5xx/408 retry hasta 3 con backoff 300/600/1200ms.
 *   - NO Idempotency-Key (GET read idempotente, RFC 7231 §4.2.1).
 *
 * NO `fetch` directo — TODO acceso a red va por `parkosFetch`.
 * NO extensión de `PRE_FLIGHT_PATHS` (DEC-SUC-03 + F3.2 verbatim):
 * `/empresa/*` GET read idempotente NO requiere pre-flight gate.
 */
import { ParkosHttpError, parkosFetch } from '@parkos/ui-kit/fetch';

/** Path backend HU-F1.4 — `empresa.py:179-213`. */
const TARIFAS_PATH = '/api/v1/empresa/tarifas-sucursal';

/**
 * Shape de una tarifa vigente — matchea backend `TarifasSucursalRead`
 * (`schemas/empresa.py:265-280`). `valor` es `number | null` (NUMERIC(18,4)
 * en DB, nullable por regla de borrado lógico: tarifa cerrada deja
 * `valor: null` en `vigente_hasta`). El consumidor del hook filtra
 * defensivamente en `useTarifasVigentes` antes de pasar a `<TarifaBadge>`.
 */
export interface TarifaSucursalRead {
  uuid: string;
  uuid_sucursal: string | null;
  uuid_tipo_vehiculo: string | null;
  uuid_tipo_tarifa: string | null;
  valor: number | null;
  valor_plena: number | null;
  vigente_desde: string;
  vigente_hasta: string | null;
  estado: string;
  created_at: string;
  created_by: string | null;
  sync_status: string | null;
}

/**
 * Page-shaped response — matchea `TarifasSucursalReadList` del backend.
 * `next_cursor` es `null` cuando no hay más páginas; el cliente NO
 * pagina porque el dataset por sucursal cabe en `limit=50`.
 */
export interface TarifasSucursalReadList {
  items: TarifaSucursalRead[];
  next_cursor: string | null;
}

/**
 * GET /api/v1/empresa/tarifas-sucursal?vigente_en=<iso>&cursor=...
 *
 * Mapeo de errores:
 *   - 200 OK → `TarifasSucursalReadList` (paginated).
 *   - 404 Not Found → `{items:[], next_cursor:null}` (sucursal sin tarifas
 *     configuradas — estado válido, NO error; DEC-F4.2-03 verbatim).
 *   - 401 → propaga `ParkosHttpError` (parkosFetch handle401 Mutex refresh-once).
 *   - 5xx / network → propaga `ParkosHttpError` (parkosFetch retry 3x backoff).
 *   - 403 → propaga `ParkosHttpError` (permission denied, F1.x invariant).
 */
export async function listTarifasSucursal(
  vigenteEn: Date = new Date(),
  cursor?: string,
): Promise<TarifasSucursalReadList> {
  const params = new URLSearchParams({ vigente_en: vigenteEn.toISOString() });
  if (cursor) params.set('cursor', cursor);
  try {
    return await parkosFetch<TarifasSucursalReadList>(
      `${TARIFAS_PATH}?${params.toString()}`,
    );
  } catch (err) {
    if (err instanceof ParkosHttpError && err.status === 404) {
      return { items: [], next_cursor: null };
    }
    throw err;
  }
}
