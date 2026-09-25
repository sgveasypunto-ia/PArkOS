/**
 * `clienteApi.ts` — fetch cliente + subscripcion metadata for the
 * tiquete de entrada preview (HU-INGRESO-SIN-PLACA follow-up).
 *
 * REGRESSION fix (2026-09-22): when an ingreso has a
 * ``uuid_subscripcion_cliente``, the tiquete preview should display
 * the cliente's name + identificador + a ``*** PAGO CON MENSUALIDAD
 * ***`` sello (DEC-SUC-21). The backend's POST /ingresos response
 * only carries the FK; the renderer needs to hydrate the cliente
 * metadata via two chained reads:
 *
 *   1. ``GET /api/v1/clientes/subscripciones-cliente/{uuid}`` → FK
 *      ``uuid_cliente`` + ``fecha_vencimiento`` + ``uuid_tipo_subscripcion``.
 *   2. ``GET /api/v1/clientes/clientes/{uuid_cliente}`` → ``nombre``,
 *      ``apellido``, ``tipo_identificador``, ``numero_identificacion``.
 *
 * This module wraps those two reads into a single ``getClienteBySubscripcion``
 * helper + a SWR-backed ``useClienteBySubscripcion`` hook so the
 * TiqueteModal preview can render the cliente block without the parent
 * having to thread props through manually.
 *
 * FEATURE EXTENSION (2026-09-22 — A+B+C workflow): the response now
 * carries ``fechaVencimiento`` + ``uuidTipoSubscripcion`` so the
 * tiquete preview can warn the operator when the subscription is
 * expired (``fechaVencimiento < today``) and gate the "Imprimir"
 * button accordingly (DEC-SUC-21 — no tiquete with an invalid
 * subscription). Plan name resolution is a follow-up (requires a
 * ``GET /clientes/tipo-subscripciones/{uuid}`` chain).
 */
import useSWR from 'swr';

import { parkosFetch } from '@parkos/ui-kit/fetch';

const SUBSCRIPCIONES_PATH = '/api/v1/clientes/subscripciones-cliente';
const CLIENTES_PATH = '/api/v1/clientes/clientes';

interface SubscripcionRow {
  uuid: string;
  uuid_cliente: string | null;
  uuid_tipo_subscripcion: string | null;
  /** Subscription coverage window — surface warning in preview if
      expired (operator-side gate per DEC-SUC-21). */
  fecha_inicio_cobertura: string | null;
  fecha_vencimiento: string | null;
  vigente_desde: string;
  vigente_hasta: string | null;
  estado: string;
}

interface ClienteRow {
  uuid: string;
  tipo_identificador: string | null;
  numero_identificacion: string | null;
  nombre: string | null;
  apellido: string | null;
}

/**
 * Expanded cliente context — the original (HU-INGRESO-SIN-PLACA
 * preview) fields plus subscription coverage + plan FK for the
 * A+B+C workflow features. Fields default to ``null`` when the
 * backend response doesn't include them — never throws.
 */
export interface ClienteContext {
  nombre: string;
  apellido: string;
  // Espejo de solo lectura de `Clientes.tipo_identificador` (backend
  // `Literal["NIT", "CC", "CE", "pasaporte"]`). Fix 2026-09-25: este
  // campo declaraba `'PAS'` como variante — el backend nunca emite ese
  // código (usa `'pasaporte'`, ver `facturaApi.ts`/`facturaServicioApi.ts`),
  // así que `'PAS'` nunca podía matchear nada; queda como `string` porque
  // este dato es puramente de display (preview del tiquete), no un
  // discriminador sobre el que se ramifique lógica.
  tipoIdentificador: string;
  numeroIdentificacion: string;
  /** ISO date string — ``null`` when the subscription has no
      ``fecha_vencimiento``. */
  fechaVencimiento: string | null;
  /** FK to ``prod.tipo_subscripciones`` — resolved plan name is a
      follow-up (needs an extra GET to ``/clientes/tipo-subscripciones/{uuid}``). */
  uuidTipoSubscripcion: string | null;
  /** ``true`` when the subscription is active (``vigente_hasta IS NULL``
      AND ``fecha_vencimiento >= today`` AND ``estado === 'activo'``). */
  suscripcionVigente: boolean;
}

/**
 * `getClienteBySubscripcion(uuidSubscripcion)` — chained read of
 * subscripcion → cliente, returns a typed `ClienteContext` (or
 * `null` if either leg returns no vigente row).
 *
 * 404 from either leg → `null` (operator-side fallback: tiquete
 * renders without the cliente block; preview shows "—").
 */
export async function getClienteBySubscripcion(
  uuidSubscripcion: string,
): Promise<ClienteContext | null> {
  const subResponse = await parkosFetch<SubscripcionRow[] | { items: SubscripcionRow[] }>(
    `${SUBSCRIPCIONES_PATH}/${uuidSubscripcion}`,
  );
  const subList: SubscripcionRow[] = Array.isArray(subResponse)
    ? subResponse
    : (subResponse as { items: SubscripcionRow[] }).items ?? [];
  const sub = subList[0];
  if (!sub || !sub.uuid_cliente) return null;

  const cliResponse = await parkosFetch<ClienteRow[] | { items: ClienteRow[] }>(
    `${CLIENTES_PATH}/${sub.uuid_cliente}`,
  );
  const cliList: ClienteRow[] = Array.isArray(cliResponse)
    ? cliResponse
    : (cliResponse as { items: ClienteRow[] }).items ?? [];
  const cli = cliList[0];
  if (!cli) return null;

  // DEC-SUC-21 validity check: subscription must be open
  // (``vigente_hasta IS NULL``) AND not expired (``fecha_vencimiento
  // IS NULL OR fecha_vencimiento >= today``) AND ``estado === 'activo'``.
  const today = new Date().toISOString().slice(0, 10);
  const notExpired =
    sub.fecha_vencimiento === null || sub.fecha_vencimiento >= today;
  const isOpen = sub.vigente_hasta === null;
  const suscripcionVigente = isOpen && notExpired && sub.estado === 'activo';

  return {
    nombre: cli.nombre ?? '',
    apellido: cli.apellido ?? '',
    tipoIdentificador: cli.tipo_identificador ?? 'CC',
    numeroIdentificacion: cli.numero_identificacion ?? '',
    fechaVencimiento: sub.fecha_vencimiento,
    uuidTipoSubscripcion: sub.uuid_tipo_subscripcion,
    suscripcionVigente,
  };
}

/**
 * `useClienteBySubscripcion(uuidSubscripcion)` — SWR-backed hook that
 * fetches the cliente metadata. Returns:
 *   - `data: ClienteContext | null` when the fetch resolves
 *   - `isLoading: true` while in flight
 *   - `error: Error | undefined` on failure
 *
 * SWR key is `null` when ``uuidSubscripcion`` is falsy (no-op
 * subscription, e.g. rotación ingreso). DedupingInterval 5min — the
 * cliente metadata rarely changes.
 */
export function useClienteBySubscripcion(
  uuidSubscripcion: string | null | undefined,
): {
  data: ClienteContext | null | undefined;
  isLoading: boolean;
  error: Error | undefined;
} {
  const key = uuidSubscripcion ? `cliente-by-subscripcion/${uuidSubscripcion}` : null;
  const swr = useSWR<ClienteContext | null>(
    key,
    () => (uuidSubscripcion ? getClienteBySubscripcion(uuidSubscripcion) : Promise.resolve(null)),
    {
      dedupingInterval: 5 * 60 * 1000,
      revalidateOnFocus: false,
    },
  );
  return {
    data: swr.data,
    isLoading: swr.isLoading,
    error: swr.error,
  };
}
