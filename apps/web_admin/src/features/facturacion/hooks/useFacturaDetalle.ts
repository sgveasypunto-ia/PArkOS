/**
 * `useFacturaDetalle.ts` — SWR composition for the HU-X drill-down page
 * (REQ-X-02..07 of `facturacion-admin/spec.md`).
 *
 * Six parallel SWR fetches in one call:
 *   - `header`    — `GET /facturacion/facturas/{uuid}` (the drill-down BE endpoint)
 *   - `detalle`   — `GET /facturacion/factura-detalle?uuid_factura=...`
 *   - `impuestos` — `GET /facturacion/factura-impuestos?uuid_factura=...`
 *   - `pagos`     — `GET /facturacion/factura-pagos?uuid_factura=...` (X.1a fix)
 *   - `fe`        — `GET /facturacion/factura-electronica/{uuid}` (optional)
 *   - `hash`      — `GET /admin/log-transaccional?tabla_afectada=factura&limit=20`
 *                   (filtered client-side for the matching `uuid_referencia`)
 *
 * The page composes 6 sections from these — one per query above. Each
 * returns an SWR `{data, error, isLoading, mutate}` so the page can
 * render per-section loaders/errors (REQ-X-11: errors are NOT fatal
 * global). When `uuid` is null (the route param is loading), every
 * SWR key is `null` and no fetch happens.
 *
 * `revalidateOnFocus: false` — manual navigation only; the page calls
 * `mutate(swrKey)` after each action (reimprimir, anular, reclamo) per
 * REQ-X-XR1.
 */
import useSWR from 'swr';

import {
  fetchFacturaByUuid,
  fetchFacturaDetalle,
  fetchFacturaElectronicaByUuid,
  fetchFacturaHash,
  fetchFacturaImpuestos,
  fetchFacturaPagos,
  type FacturaDetailRead,
  type FacturaDetalleList,
  type FacturaElectronicaRead,
  type FacturaImpuestoList,
  type FacturaPagoList,
  type LogTransaccionalList,
} from '../api/facturacionAdminApi';

const STALE = { revalidateOnFocus: false, dedupingInterval: 30_000 };

// ---------------------------------------------------------------------------
// SWR key builders (exported for test mocks + manual mutate calls)
// ---------------------------------------------------------------------------

export function facturaHeaderKey(uuid: string): readonly unknown[] {
  return ['factura', uuid] as const;
}

export function facturaDetalleKey(uuid: string): readonly unknown[] {
  return ['factura-detalle', uuid] as const;
}

export function facturaImpuestosKey(uuid: string): readonly unknown[] {
  return ['factura-impuestos', uuid] as const;
}

export function facturaPagosKey(uuid: string): readonly unknown[] {
  return ['factura-pagos', uuid] as const;
}

export function facturaFeKey(feUuid: string): readonly unknown[] {
  return ['factura-electronica', feUuid] as const;
}

export function facturaHashKey(uuid: string): readonly unknown[] {
  return ['factura-hash', uuid] as const;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * `useFacturaDetalle(uuid)` — single composition hook for the page.
 *
 * Returns the 6 SWR responses. `header.data` carries the `uuid_factura_electronica`
 * reference needed to fetch the FE row; the FE SWR is only triggered
 * when the header is loaded AND it points to a non-null FE uuid.
 */
export function useFacturaDetalle(uuid: string | null): {
  header: ReturnType<typeof useSWR<FacturaDetailRead>>;
  detalle: ReturnType<typeof useSWR<FacturaDetalleList>>;
  impuestos: ReturnType<typeof useSWR<FacturaImpuestoList>>;
  pagos: ReturnType<typeof useSWR<FacturaPagoList>>;
  fe: ReturnType<typeof useSWR<FacturaElectronicaRead>>;
  hash: ReturnType<typeof useSWR<LogTransaccionalList>>;
} {
  const header = useSWR<FacturaDetailRead>(
    uuid ? facturaHeaderKey(uuid) : null,
    () => fetchFacturaByUuid(uuid as string),
    STALE,
  );
  const detalle = useSWR<FacturaDetalleList>(
    uuid ? facturaDetalleKey(uuid) : null,
    () => fetchFacturaDetalle(uuid as string),
    STALE,
  );
  const impuestos = useSWR<FacturaImpuestoList>(
    uuid ? facturaImpuestosKey(uuid) : null,
    () => fetchFacturaImpuestos(uuid as string),
    STALE,
  );
  const pagos = useSWR<FacturaPagoList>(
    uuid ? facturaPagosKey(uuid) : null,
    () => fetchFacturaPagos(uuid as string),
    STALE,
  );
  // FE only fires when header loaded and points to a real FE uuid. The
  // GET /factura-electronica/{uuid} endpoint takes the FE uuid (NOT the
  // factura uuid). The shape `uuid_factura_electronica` is OPTIONAL in
  // the display — when the factura has no FE row, the SWR key is null
  // and the page renders the "FE no generada" card.
  const feUuid = header.data?.uuid as string | undefined;
  const fe = useSWR<FacturaElectronicaRead>(
    feUuid ? facturaFeKey(feUuid) : null,
    () => fetchFacturaElectronicaByUuid(feUuid as string),
    STALE,
  );
  const hash = useSWR<LogTransaccionalList>(
    uuid ? facturaHashKey(uuid) : null,
    () => fetchFacturaHash(uuid as string),
    STALE,
  );
  return { header, detalle, impuestos, pagos, fe, hash };
}
