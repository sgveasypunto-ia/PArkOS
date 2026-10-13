/**
 * `facturacionAdminApi.ts` — HTTP client for the HU-X web-admin drill-down
 * surface (`/facturacion/:uuid`, REQ-X-01..07 of `facturacion-admin/spec.md`).
 *
 * Five endpoints consumed (all branch API `parkos-api-admin:8000`):
 *
 *   GET /api/v1/facturacion/facturas/{uuid}                       (header)
 *   GET /api/v1/facturacion/factura-detalle?uuid_factura=...       (items)
 *   GET /api/v1/facturacion/factura-impuestos?uuid_factura=...     (taxes)
 *   GET /api/v1/facturacion/factura-pagos?uuid_factura=...         (payments, X.1a fix)
 *   GET /api/v1/facturacion/factura-electronica/{uuid}             (FE block, optional)
 *
 * The drill-down page composes data from all five via
 * `useFacturaDetalle(uuid)` (single React hook, 6 parallel SWR fetches
 * incl. the hash). Each function here is a thin transport that runs the
 * response through a Zod schema before returning — wire drift surfaces
 * as a parse error, never a silent `undefined` in the UI.
 *
 * The legacy `apps/electron-sucursal/src/features/facturacion/api/
 * facturaApi.ts` uses `parkosFetch` with the Zod schema in a third arg.
 * This client uses the simpler `parkosFetch<T>` from
 * `@/lib/fetch` (web-admin) and runs the schema manually for clarity.
 */
import { parkosFetchRaw, type ParkosFetchInit } from '@/lib/fetch';

import {
  facturaDetailReadSchema,
  facturaDetalleListSchema,
  facturaElectronicaReadSchema,
  facturaImpuestoListSchema,
  facturaPagoListSchema,
  logTransaccionalListSchema,
  type FacturaDetailRead,
  type FacturaDetalleList,
  type FacturaElectronicaRead,
  type FacturaImpuestoList,
  type FacturaPagoList,
  type LogTransaccionalList,
} from './facturacionAdminSchema';

/**
 * `facturacionHttpError` — typed Error thrown on non-2xx responses.
 * Carries the HTTP status so the page can decide between 404 (mostrar
 * "Factura no encontrada") and 5xx (mostrar "Error al cargar"). Mirrors
 * the `ParkosHttpError` shape from `@parkos/ui-kit/fetch` but the FE
 * surface expects a plain Error with an attached `.status` getter.
 */
export class FacturacionHttpError extends Error {
  readonly status: number;
  readonly body: string;
  constructor(status: number, body: string, message?: string) {
    super(message ?? `facturacionAdminApi: ${status} ${body.slice(0, 200)}`);
    this.status = status;
    this.body = body;
    this.name = 'FacturacionHttpError';
  }
}

/**
 * `fetchJson` — internal helper. Throws `FacturacionHttpError` on
 * non-2xx, otherwise parses JSON and runs it through the supplied
 * Zod schema. The schema is REQUIRED (defense in depth — the BE
 * Pydantic could regress; the FE parse catches it).
 */
async function fetchJson<T>(
  input: string,
  init: ParkosFetchInit,
  schema: { parse: (raw: unknown) => T },
): Promise<T> {
  const res = await parkosFetchRaw(input, init);
  if (!res.ok) {
    const body = await res.text();
    throw new FacturacionHttpError(
      res.status,
      body,
      `facturacionAdminApi: ${init.method ?? 'GET'} ${input} -> ${res.status}`,
    );
  }
  const raw = await res.json();
  return schema.parse(raw);
}

// ---------------------------------------------------------------------------
// Factura header
// ---------------------------------------------------------------------------

/**
 * `fetchFacturaByUuid(uuid)` — header for the drill-down page.
 *
 * Calls `GET /api/v1/facturacion/facturas/{uuid}` (the factory mount,
 * plural). Returns the raw `prod.facturas` row (no display enrichment —
 * see REQ-X-03 for the MVP "Consumidor final" decision).
 */
export async function fetchFacturaByUuid(uuid: string): Promise<FacturaDetailRead> {
  return fetchJson<FacturaDetailRead>(
    `/api/v1/facturacion/facturas/${uuid}`,
    { method: 'GET', headers: { Accept: 'application/json' } },
    facturaDetailReadSchema,
  );
}

// ---------------------------------------------------------------------------
// Items / impuestos / pagos — all use ?uuid_factura=...
// ---------------------------------------------------------------------------

/**
 * `fetchFacturaDetalle(uuidFactura)` — invoice line items.
 * `GET /api/v1/facturacion/factura-detalle?uuid_factura=...`.
 *
 * NOTE: as of HU-X.1a, this endpoint does NOT honour `?uuid_factura=`
 * (the factory ignores it — same bug as the pagos endpoint). The
 * filter is still applied client-side in the SWR key to keep the URL
 * semantic; the page filters items by `item.uuid_factura === uuid` as
 * a safety net.
 */
export async function fetchFacturaDetalle(
  uuidFactura: string,
): Promise<FacturaDetalleList> {
  return fetchJson<FacturaDetalleList>(
    `/api/v1/facturacion/factura-detalle?uuid_factura=${uuidFactura}`,
    { method: 'GET', headers: { Accept: 'application/json' } },
    facturaDetalleListSchema,
  );
}

/**
 * `fetchFacturaImpuestos(uuidFactura)` — IVA rows for a factura.
 * `GET /api/v1/facturacion/factura-impuestos?uuid_factura=...`.
 */
export async function fetchFacturaImpuestos(
  uuidFactura: string,
): Promise<FacturaImpuestoList> {
  return fetchJson<FacturaImpuestoList>(
    `/api/v1/facturacion/factura-impuestos?uuid_factura=${uuidFactura}`,
    { method: 'GET', headers: { Accept: 'application/json' } },
    facturaImpuestoListSchema,
  );
}

/**
 * `fetchFacturaPagos(uuidFactura)` — payment events for a factura.
 * `GET /api/v1/facturacion/factura-pagos?uuid_factura=...` (X.1a fix).
 *
 * Pre-fix: factory silently dropped the param and returned the global
 * list. Post-fix: the WHERE honours the param. Tenant scope is enforced
 * by the `do_orm_execute` listener on `FacturaPagos.uuid_sucursal`.
 */
export async function fetchFacturaPagos(
  uuidFactura: string,
): Promise<FacturaPagoList> {
  return fetchJson<FacturaPagoList>(
    `/api/v1/facturacion/factura-pagos?uuid_factura=${uuidFactura}`,
    { method: 'GET', headers: { Accept: 'application/json' } },
    facturaPagoListSchema,
  );
}

// ---------------------------------------------------------------------------
// FE block
// ---------------------------------------------------------------------------

/**
 * `fetchFacturaElectronicaByUuid(uuid)` — FE row by uuid.
 * `GET /api/v1/facturacion/factura-electronica/{uuid}`.
 *
 * Returns 404 (`FacturacionHttpError` with `.status === 404`) when the
 * factura has no FE row yet. The page catches 404 and renders the
 * "FE no generada" card. Caller responsibility.
 */
export async function fetchFacturaElectronicaByUuid(
  uuid: string,
): Promise<FacturaElectronicaRead> {
  return fetchJson<FacturaElectronicaRead>(
    `/api/v1/facturacion/factura-electronica/${uuid}`,
    { method: 'GET', headers: { Accept: 'application/json' } },
    facturaElectronicaReadSchema,
  );
}

/**
 * `fetchFacturaElectronicaByFacturaUuid(uuidFactura)` — HU-X.8: resolve
 * the FE row from the parent `prod.facturas.uuid`.
 *
 * `GET /api/v1/facturacion/factura-electronica?uuid_factura=…` (note:
 * the path param `{uuid}` in the route is intentionally ignored in this
 * branch; the BE handler resolves the FE uuid from the parent lookup).
 *
 * The admin drill-down page uses this so the FE card renders without
 * needing to know the FE uuid a priori. Returns 404 with error
 * `factura_sin_fe` when the parent has no FE row (distinct from
 * `factura_electronica_no_encontrada` which the path-based variant
 * returns for an unknown FE uuid).
 */
export async function fetchFacturaElectronicaByFacturaUuid(
  uuidFactura: string,
): Promise<FacturaElectronicaRead> {
  return fetchJson<FacturaElectronicaRead>(
    `/api/v1/facturacion/factura-electronica?uuid_factura=${encodeURIComponent(uuidFactura)}`,
    { method: 'GET', headers: { Accept: 'application/json' } },
    facturaElectronicaReadSchema,
  );
}

// ---------------------------------------------------------------------------
// Hash chain (header card)
// ---------------------------------------------------------------------------

/**
 * `fetchFacturaHash(_uuidFactura)` — last `log_transaccional` rows for the
 * factura, used to display the `hash_actual` in the header card.
 *
 * `GET /api/v1/admin/log-transaccional?tabla_afectada=factura&limit=20`
 * (filtered client-side by `uuid_referencia === uuid` via
 * `findHashForFactura`). Uses the admin endpoint (cross-branch,
 * admin-only — same surface the `/auditoria/log` page consumes).
 *
 * The `uuidFactura` arg is reserved for a future BE filter (the
 * `?uuid_referencia=…` query param is not yet exposed). The leading
 * underscore silences `@typescript-eslint/no-unused-vars` until then.
 */
export async function fetchFacturaHash(
  _uuidFactura: string,
): Promise<LogTransaccionalList> {
  return fetchJson<LogTransaccionalList>(
    `/api/v1/admin/log-transaccional?tabla_afectada=factura&limit=20`,
    { method: 'GET', headers: { Accept: 'application/json' } },
    logTransaccionalListSchema,
  );
}

/**
 * `findHashForFactura(uuidFactura, list)` — narrow the admin log
 * list to the entry whose `uuid_referencia` matches the factura. The
 * admin endpoint doesn't accept a `uuid_referencia` filter (read at
 * the BE in this turn — X.1b may add a dedicated filter). The page
 * does the filter client-side; 20 items is the BE's max for this
 * endpoint.
 */
export function findHashForFactura(
  uuidFactura: string,
  list: LogTransaccionalList,
): string | null {
  for (const item of list.items) {
    if (item.uuid_referencia === uuidFactura) {
      return item.hash_actual;
    }
  }
  return null;
}
