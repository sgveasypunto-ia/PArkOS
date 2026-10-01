/**
 * catalogApi — Cliente HTTP para los 9 endpoints C+Q+U de catálogos.
 *
 * Mounted por `backend/.../api/v1/catalogos.py` (PR3) con el patrón
 * `_mount_catalog`: mismo shape para los 9 (`GET`, `POST`, `PUT
 * /{uuid}`), sin DELETE (close+insert bi-temporal). Issuer
 * `admin-,operador-` + permission `config_catalogo` enforced en el
 * backend; acá solo cableamos el transporte.
 *
 * Sin sucursal en el path: los 9 catálogos son tenant-globales
 * (DEC-CATALOG-01). Esta capa NO inyecta `X-Sucursal-Context`.
 */
import { parkosFetch } from '@/lib/fetch';

export const CATALOG_RESOURCES = [
  'tipo-persona',
  'tipos-vehiculo',
  'tipo-subscripciones',
  'tipo-tarifa',
  'tipo-sucursal',
  'tipo-arqueo',
  'impuestos',
  'otros-cobros',
  'costos-servicios',
] as const;

export type CatalogResource = (typeof CATALOG_RESOURCES)[number];

export interface CatalogRow {
  uuid: string;
  vigente_desde: string;
  vigente_hasta: string | null;
  estado: 'activo' | 'inactivo';
  [key: string]: unknown;
}

interface ListEnvelope {
  items: CatalogRow[];
}

/**
 * Headers para mutacionales. parkosFetch ya setea
 * `Content-Type: application/json` cuando detecta body, pero ser
 * explícito previene la clase de bug donde el body se serializa
 * mal y el server termina parseando `{}` vacío (422 Unprocessable).
 * El patrón mirror está en
 * `features/tipos-vehiculo/api/tiposVehiculoApi.ts:32`.
 */
const JSON_HEADERS = {
  'Content-Type': 'application/json',
  Accept: 'application/json',
} as const;

export async function listCatalog(resource: CatalogResource): Promise<CatalogRow[]> {
  const envelope = await parkosFetch<ListEnvelope>(
    `/api/v1/catalogos/${resource}`,
    { method: 'GET' },
  );
  return envelope.items;
}

export async function createCatalogVersion(
  resource: CatalogResource,
  payload: Record<string, unknown>,
): Promise<CatalogRow> {
  return parkosFetch<CatalogRow>(`/api/v1/catalogos/${resource}`, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(payload),
  });
}

export async function updateCatalogVersion(
  resource: CatalogResource,
  uuid: string,
  payload: Record<string, unknown>,
): Promise<CatalogRow> {
  return parkosFetch<CatalogRow>(`/api/v1/catalogos/${resource}/${uuid}`, {
    method: 'PUT',
    headers: JSON_HEADERS,
    body: JSON.stringify(payload),
  });
}
