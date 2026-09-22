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
 *      ``uuid_cliente`` (and optionally plan metadata).
 *   2. ``GET /api/v1/clientes/clientes/{uuid_cliente}`` → ``nombre``,
 *      ``apellido``, ``tipo_identificador``, ``numero_identificacion``.
 *
 * This module wraps those two reads into a single ``getClienteBySubscripcion``
 * helper + a SWR-backed ``useClienteBySubscripcion`` hook so the
 * TiqueteModal preview can render the cliente block without the parent
 * having to thread props through manually.
 */
import useSWR from 'swr';

import { parkosFetch } from '@parkos/ui-kit/fetch';

import type { ClienteContext } from '@/lib/print/printBuilder';

const SUBSCRIPCIONES_PATH = '/api/v1/clientes/subscripciones-cliente';
const CLIENTES_PATH = '/api/v1/clientes/clientes';

interface SubscripcionRow {
  uuid: string;
  uuid_cliente: string | null;
  /** F1.12 plan metadata — surface in tiquete later if needed. */
  uuid_plan: string | null;
}

interface ClienteRow {
  uuid: string;
  tipo_identificador: string | null;
  numero_identificacion: string | null;
  nombre: string | null;
  apellido: string | null;
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

  return {
    nombre: cli.nombre ?? '',
    apellido: cli.apellido ?? '',
    tipoIdentificador: cli.tipo_identificador ?? 'CC',
    numeroIdentificacion: cli.numero_identificacion ?? '',
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
