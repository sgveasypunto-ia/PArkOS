/**
 * `tiposVehiculoApi.ts` — HTTP layer para el catálogo de tipos de vehículo
 * (HU-F4.1, T2 — primer consumer del feature `catalogos`).
 *
 * Backend (F1.x ya shipped, READ ONLY):
 *   - `GET /api/v1/catalogos/tipos-vehiculo` (catalogos.py:140-147,
 *     `_mount_catalog(resource="tipos-vehiculo", ...)`).
 *   - Permission `config_catalogo` per `_CATALOG_DEFAULTS:101`.
 *   - Response shape `TiposVehiculoRead` (`schemas/tipos_vehiculo.py:13-23`):
 *     `{ uuid, tipo, vigente_desde, vigente_hasta, estado, ... }`.
 *
 * DEC-F4.1-09 (cliente): el campo `tipo` es `string | null` porque el
 * backend Pydantic lo permite (`tipo: str | None`). Filtramos
 * defensivamente cualquier fila con `tipo: null` ANTES de exponer al hook
 * — un catálogo corrupto (fila con `tipo: null` por bug backend legacy)
 * nunca llega al consumidor del SWR.
 *
 * 404 → `[]` (DEC-F4.1-04 + precedent F3.3 `getSesionActiva`): sucursal
 * nueva sin tipos configurados es estado válido, NO error. SWR
 * `shouldRetryOnError` excluye 404 → no retry spam.
 *
 * El wrapper `parkosFetch` añade (F2.2 invariant):
 *   - Authorization Bearer desde `authStore` (auto).
 *   - 401 refresh-once via Mutex `refreshAccessToken()` (DEC-FETCH-03).
 *   - 5xx/408 retry hasta 3 con backoff 300/600/1200ms.
 *   - NO Idempotency-Key (GET read idempotente, RFC 7231 §4.2.1).
 *
 * NO `fetch` directo — TODO acceso a red va por `parkosFetch`.
 * NO extensión de `PRE_FLIGHT_PATHS` (DEC-SUC-03 + F3.2 verbatim):
 * `/catalogos/*` GET read idempotente NO requiere pre-flight gate.
 */
import { ParkosHttpError, parkosFetch } from '@parkos/ui-kit/fetch';

/** Path GET catálogo de tipos de vehículo (F1.x backend shipped). */
const TIPOS_VEHICULO_PATH = '/api/v1/catalogos/tipos-vehiculo';

/**
 * Shape de un tipo de vehículo — matchea backend `TiposVehiculoRead`
 * (`schemas/tipos_vehiculo.py:13-23`). `tipo` es nullable en backend;
 * el filtro defensivo en `getTiposVehiculo()` descarta filas con
 * `tipo: null` antes de retornar al hook.
 */
export interface TipoVehiculo {
  uuid: string;
  tipo: string | null;
  vigente_desde: string;
  vigente_hasta: string | null;
  estado: string;
}

/**
 * GET /api/v1/catalogos/tipos-vehiculo.
 *
 * Mapeo de errores:
 *   - 200 OK → `TipoVehiculo[]` filtrado (descarta `tipo: null` defensivo).
 *   - 404 Not Found → `[]` (sucursal nueva sin tipos — estado válido, NO error).
 *   - 401 → propaga `ParkosHttpError` (parkosFetch handle401 Mutex refresh-once).
 *   - 5xx / network → propaga `ParkosHttpError` (parkosFetch retry 3x backoff).
 *   - 403 → propaga `ParkosHttpError` (permission denied, F1.x invariant).
 */
export async function getTiposVehiculo(): Promise<TipoVehiculo[]> {
  try {
    const items = await parkosFetch<TipoVehiculo[]>(TIPOS_VEHICULO_PATH);
    return items.filter((t) => t.tipo !== null);
  } catch (err) {
    if (err instanceof ParkosHttpError && err.status === 404) {
      return [];
    }
    throw err;
  }
}
