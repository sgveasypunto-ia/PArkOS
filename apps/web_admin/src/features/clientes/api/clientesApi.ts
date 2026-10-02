/**
 * `clientesApi.ts` — HTTP client for the HU-F20.1 clientes directory
 * (web_admin). Mirrors `features/audit/api/auditApi.ts`'s style: thin
 * wrapper over `parkosFetchRaw`, Zod-parsed responses.
 *
 * Endpoints consumed (all mounted via `router_factory.make_router`,
 * `permission_required="gestionar_clientes"`):
 *
 *   - `GET/PUT  /api/v1/clientes/clientes/{uuid}`     -- cliente detail/update
 *   - `GET      /api/v1/clientes/clientes`            -- cliente list
 *   - `GET      /api/v1/clientes/subscripciones-cliente[/{uuid}/history]`
 *   - `GET      /api/v1/clientes/subscripcion-vehiculos`
 *   - `GET      /api/v1/clientes/vehiculos`
 *
 * IMPORTANT path correction vs. the original task brief: the brief
 * assumed the cliente resource's base path is `/api/v1/clientes`. That
 * is wrong -- verified against `api/v1/clientes.py`: the outer router
 * already carries `prefix="/clientes"`, and `_mount_cliente(resource=
 * "clientes", ...)` mounts `router_factory.make_router(resource=
 * "clientes", ...)`, which creates ITS OWN `prefix="/clientes"` --
 * combining to `/api/v1/clientes/clientes` (confirmed live by
 * `backend/tests/integration/test_clientes_family_permission_codes.py`
 * and `test_versioned_update_preserves_unset_fields.py`, both of which
 * POST/PUT against literally `/api/v1/clientes/clientes`). The other 3
 * resources ("vehiculos", "subscripciones-cliente",
 * "subscripcion-vehiculos") don't collide with the outer "/clientes"
 * prefix, so their paths ARE exactly `/api/v1/clientes/<resource>` as
 * briefed.
 *
 * Pagination note (shared by every list endpoint here): the generic
 * `make_router`-mounted list endpoint accepts ONLY `cursor`/`limit` (max
 * 200) -- the `*Filter` Pydantic schemas in `schemas/clientes.py`
 * (`ClientesFilter`, `SubscripcionesClienteFilter`, etc.) exist but are
 * dead code, never wired into `router_factory.make_router`. Every
 * "by X" lookup below is therefore a client-side full-scan-then-filter
 * over up to `maxPages * limit` rows -- see `fetchAllPages` and its
 * callers. This is a known scaling caveat (out of scope to fix here:
 * `router_factory.py` is shared by many unrelated resources); a real
 * fix is wiring the existing `*Filter` schemas into the factory.
 */
import { parkosFetchRaw, type ParkosFetchInit } from '@parkos/ui-kit/fetch';
import { z } from 'zod';

const CLIENTES_PATH = '/api/v1/clientes/clientes';
const VEHICULOS_PATH = '/api/v1/clientes/vehiculos';
const SUBSCRIPCIONES_CLIENTE_PATH = '/api/v1/clientes/subscripciones-cliente';
const SUBSCRIPCION_VEHICULOS_PATH = '/api/v1/clientes/subscripcion-vehiculos';

async function fetchJson<T>(input: string, init: ParkosFetchInit): Promise<T> {
  const res = await parkosFetchRaw(input, init);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(
      `clientesApi: ${init.method ?? 'GET'} ${input} -> ${res.status}: ${body.slice(0, 200)}`,
    );
  }
  return (await res.json()) as T;
}

const getHeaders = { Accept: 'application/json' };
const jsonHeaders = { Accept: 'application/json', 'Content-Type': 'application/json' };

// ---------------------------------------------------------------------------
// Clientes
// ---------------------------------------------------------------------------

export const clienteSchema = z.object({
  uuid: z.string().uuid(),
  tipo_identificador: z.string().nullable(),
  numero_identificacion: z.string().nullable(),
  nombre: z.string().nullable(),
  apellido: z.string().nullable(),
  telefono: z.string().nullable(),
  email: z.string().nullable(),
  uuid_tipo_persona: z.string().uuid().nullable(),
  registro: z.record(z.unknown()).nullable(),
  vigente_desde: z.string(),
  vigente_hasta: z.string().nullable(),
  estado: z.string(),
  created_at: z.string(),
  created_by: z.string().uuid().nullable(),
  sync_status: z.string().nullable(),
});
export type Cliente = z.infer<typeof clienteSchema>;

export const clienteListSchema = z.object({
  items: z.array(clienteSchema),
  next_cursor: z.string().nullable(),
});
export type ClienteListResponse = z.infer<typeof clienteListSchema>;

// Mirrors `ClientesUpdate` (`schemas/clientes.py`): every field optional,
// `null` clears it. Frontend-only enforcement note: `tipo_identificador`
// is a plain unenforced `str | None` server-side -- the closed set below
// (CC/NIT/CE/pasaporte) is a client-side UX guardrail, not a backend
// contract (the backend accepts any string).
export const clienteUpdateSchema = z.object({
  tipo_identificador: z.string().nullable().optional(),
  numero_identificacion: z.string().nullable().optional(),
  nombre: z.string().nullable().optional(),
  apellido: z.string().nullable().optional(),
  telefono: z.string().nullable().optional(),
  email: z.string().email().nullable().optional(),
  uuid_tipo_persona: z.string().uuid().nullable().optional(),
  registro: z.record(z.unknown()).nullable().optional(),
});
export type ClienteUpdateInput = z.infer<typeof clienteUpdateSchema>;

export interface ListOpts {
  cursor?: string;
  limit?: number;
}

export async function listClientes(opts: ListOpts = {}): Promise<ClienteListResponse> {
  const params = new URLSearchParams();
  if (opts.cursor) params.set('cursor', opts.cursor);
  params.set('limit', String(opts.limit ?? 200));
  const raw = await fetchJson<unknown>(`${CLIENTES_PATH}?${params.toString()}`, {
    method: 'GET',
    headers: getHeaders,
  });
  return clienteListSchema.parse(raw);
}

export async function getCliente(uuid: string): Promise<Cliente> {
  const raw = await fetchJson<unknown>(`${CLIENTES_PATH}/${uuid}`, {
    method: 'GET',
    headers: getHeaders,
  });
  return clienteSchema.parse(raw);
}

export async function updateCliente(uuid: string, input: ClienteUpdateInput): Promise<Cliente> {
  const parsed = clienteUpdateSchema.parse(input);
  const raw = await fetchJson<unknown>(`${CLIENTES_PATH}/${uuid}`, {
    method: 'PUT',
    headers: jsonHeaders,
    body: JSON.stringify(parsed),
  });
  return clienteSchema.parse(raw);
}

// ---------------------------------------------------------------------------
// SubscripcionesCliente
// ---------------------------------------------------------------------------

export const subscripcionClienteSchema = z.object({
  uuid: z.string().uuid(),
  uuid_cliente: z.string().uuid().nullable(),
  uuid_sucursal: z.string().uuid().nullable(),
  uuid_tipo_subscripcion: z.string().uuid().nullable(),
  fecha_inicio_cobertura: z.string().nullable(),
  fecha_vencimiento: z.string().nullable(),
  // HU-F20.2 / migration 0067. `null` means "not set" -- callers that
  // need the EFFECTIVE alert window should treat `null` as the DB
  // default of 7 (CU-06 BR4), mirroring `SubscripcionesClienteRead`'s
  // own docstring server-side.
  dias_alerta_pre_vencimiento: z.number().int().nullable(),
  vigente_desde: z.string(),
  vigente_hasta: z.string().nullable(),
  estado: z.string(),
  created_at: z.string(),
  created_by: z.string().uuid().nullable(),
  sync_status: z.string().nullable(),
});
export type SubscripcionCliente = z.infer<typeof subscripcionClienteSchema>;

// HU-F20.2: mirrors `SubscripcionesClienteCreate` (`schemas/clientes.py`).
export const subscripcionClienteCreateSchema = z.object({
  uuid_cliente: z.string().uuid(),
  uuid_sucursal: z.string().uuid(),
  uuid_tipo_subscripcion: z.string().uuid(),
  fecha_inicio_cobertura: z.string(),
  fecha_vencimiento: z.string(),
  dias_alerta_pre_vencimiento: z.number().int().min(1).max(90),
});
export type SubscripcionClienteCreateInput = z.infer<typeof subscripcionClienteCreateSchema>;

// HU-F20.2: mirrors `SubscripcionesClienteUpdate` -- same shape as Create.
export const subscripcionClienteUpdateSchema = subscripcionClienteCreateSchema;
export type SubscripcionClienteUpdateInput = z.infer<typeof subscripcionClienteUpdateSchema>;

const subscripcionClienteListSchema = z.object({
  items: z.array(subscripcionClienteSchema),
  next_cursor: z.string().nullable(),
});

export async function listSubscripcionesCliente(
  opts: ListOpts = {},
): Promise<z.infer<typeof subscripcionClienteListSchema>> {
  const params = new URLSearchParams();
  if (opts.cursor) params.set('cursor', opts.cursor);
  params.set('limit', String(opts.limit ?? 200));
  const raw = await fetchJson<unknown>(`${SUBSCRIPCIONES_CLIENTE_PATH}?${params.toString()}`, {
    method: 'GET',
    headers: getHeaders,
  });
  return subscripcionClienteListSchema.parse(raw);
}

/**
 * `GET /subscripciones-cliente/{uuid}/history` -- the generic
 * `router_factory.py` history endpoint. Returns a PLAIN ARRAY (no
 * `{items, next_cursor}` envelope) of every row whose PK matches `uuid`.
 *
 * IMPORTANT LIMITATION (found while wiring `ClienteSuscripciones.tsx`,
 * kept here since it's this function's own contract): `close_and_insert`
 * (`repo/versioned.py`) REGENERATES `uuid` on every bi-temporal version,
 * so this endpoint -- which filters by `model_cls.uuid == :uuid` -- can
 * only ever return the ONE row whose PK literally is `uuid`. It cannot
 * walk back to a PRIOR closed version (whose uuid is different and
 * never surfaced anywhere in this UI). `features/tarifas/api/
 * tarifasApi.ts` hit the identical gap and got a dedicated "by-key"
 * endpoint (PR-C v2); `subscripciones-cliente` has no equivalent today.
 * Calling this per current-row uuid is still what plan.md's contract
 * asks for, so it's wired correctly and will start working the moment
 * (if ever) an equivalent by-key endpoint ships for this resource.
 */
export async function getSubscripcionClienteHistory(uuid: string): Promise<SubscripcionCliente[]> {
  const raw = await fetchJson<unknown>(`${SUBSCRIPCIONES_CLIENTE_PATH}/${uuid}/history`, {
    method: 'GET',
    headers: getHeaders,
  });
  return z.array(subscripcionClienteSchema).parse(raw);
}

/**
 * HU-F20.2 -- `POST /subscripciones-cliente` (generic C+Q+U mount, write
 * path unchanged by this HU: only the payload grows with
 * `dias_alerta_pre_vencimiento`, per plan.md HU-F20.2's own "Endpoints"
 * note).
 */
export async function createSubscripcionCliente(
  input: SubscripcionClienteCreateInput,
): Promise<SubscripcionCliente> {
  const parsed = subscripcionClienteCreateSchema.parse(input);
  const raw = await fetchJson<unknown>(SUBSCRIPCIONES_CLIENTE_PATH, {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify(parsed),
  });
  return subscripcionClienteSchema.parse(raw);
}

/** HU-F20.2 -- `PUT /subscripciones-cliente/{uuid}` (bi-temporal close+insert). */
export async function updateSubscripcionCliente(
  uuid: string,
  input: SubscripcionClienteUpdateInput,
): Promise<SubscripcionCliente> {
  const parsed = subscripcionClienteUpdateSchema.parse(input);
  const raw = await fetchJson<unknown>(`${SUBSCRIPCIONES_CLIENTE_PATH}/${uuid}`, {
    method: 'PUT',
    headers: jsonHeaders,
    body: JSON.stringify(parsed),
  });
  return subscripcionClienteSchema.parse(raw);
}

// ---------------------------------------------------------------------------
// SubscripcionVehiculos
// ---------------------------------------------------------------------------

export const subscripcionVehiculoSchema = z.object({
  uuid: z.string().uuid(),
  uuid_subscripcion_cliente: z.string().uuid().nullable(),
  uuid_vehiculo: z.string().uuid().nullable(),
  vigente_desde: z.string(),
  vigente_hasta: z.string().nullable(),
  estado: z.string(),
  created_at: z.string(),
  created_by: z.string().uuid().nullable(),
  sync_status: z.string().nullable(),
});
export type SubscripcionVehiculo = z.infer<typeof subscripcionVehiculoSchema>;

const subscripcionVehiculoListSchema = z.object({
  items: z.array(subscripcionVehiculoSchema),
  next_cursor: z.string().nullable(),
});

export async function listSubscripcionVehiculos(
  opts: ListOpts = {},
): Promise<z.infer<typeof subscripcionVehiculoListSchema>> {
  const params = new URLSearchParams();
  if (opts.cursor) params.set('cursor', opts.cursor);
  params.set('limit', String(opts.limit ?? 200));
  const raw = await fetchJson<unknown>(`${SUBSCRIPCION_VEHICULOS_PATH}?${params.toString()}`, {
    method: 'GET',
    headers: getHeaders,
  });
  return subscripcionVehiculoListSchema.parse(raw);
}

/**
 * HU-F20.2 -- `POST /subscripcion-vehiculos`. IMPORTANT: this no longer
 * hits the generic `make_router` mount -- the backend pulled
 * `subscripcion-vehiculos` writes into a DEDICATED endpoint
 * (`api/v1/clientes_subscripcion_vehiculos.py`) that validates
 * `cantidad_vehiculos_excede_plan` / `tipo_vehiculo_mixto_no_permitido` /
 * `placa_con_suscripcion_vigente` BEFORE insert (the generic mount had
 * zero pre-insert validation -- see that module's docstring). Same URL,
 * same request/response shape (`SubscripcionVehiculosCreate`/`Read`
 * reused verbatim), so this client function is unaffected by the move.
 */
export const subscripcionVehiculoCreateSchema = z.object({
  uuid_subscripcion_cliente: z.string().uuid(),
  uuid_vehiculo: z.string().uuid(),
});
export type SubscripcionVehiculoCreateInput = z.infer<typeof subscripcionVehiculoCreateSchema>;

export async function createSubscripcionVehiculo(
  input: SubscripcionVehiculoCreateInput,
): Promise<SubscripcionVehiculo> {
  const parsed = subscripcionVehiculoCreateSchema.parse(input);
  const raw = await fetchJson<unknown>(SUBSCRIPCION_VEHICULOS_PATH, {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify(parsed),
  });
  return subscripcionVehiculoSchema.parse(raw);
}

// ---------------------------------------------------------------------------
// Vehiculos
// ---------------------------------------------------------------------------

export const vehiculoSchema = z.object({
  uuid: z.string().uuid(),
  placa: z.string().nullable(),
  uuid_tipo_vehiculo: z.string().uuid().nullable(),
  vigente_desde: z.string(),
  vigente_hasta: z.string().nullable(),
  estado: z.string(),
  created_at: z.string(),
  created_by: z.string().uuid().nullable(),
  sync_status: z.string().nullable(),
});
export type Vehiculo = z.infer<typeof vehiculoSchema>;

const vehiculoListSchema = z.object({
  items: z.array(vehiculoSchema),
  next_cursor: z.string().nullable(),
});

export async function listVehiculos(opts: ListOpts = {}): Promise<z.infer<typeof vehiculoListSchema>> {
  const params = new URLSearchParams();
  if (opts.cursor) params.set('cursor', opts.cursor);
  params.set('limit', String(opts.limit ?? 200));
  const raw = await fetchJson<unknown>(`${VEHICULOS_PATH}?${params.toString()}`, {
    method: 'GET',
    headers: getHeaders,
  });
  return vehiculoListSchema.parse(raw);
}

// ---------------------------------------------------------------------------
// Shared client-side pagination/filter helpers (no server-side filter
// support -- see module docblock's "Pagination note").
// ---------------------------------------------------------------------------

const MAX_PAGES = 10;
const PAGE_LIMIT = 200;

interface PagedResponse<T> {
  items: T[];
  next_cursor: string | null;
}

async function fetchAllPages<T>(
  listFn: (opts: ListOpts) => Promise<PagedResponse<T>>,
  opts: { maxPages?: number; limit?: number } = {},
): Promise<T[]> {
  const maxPages = opts.maxPages ?? MAX_PAGES;
  const limit = opts.limit ?? PAGE_LIMIT;
  const all: T[] = [];
  let cursor: string | undefined;
  for (let page = 0; page < maxPages; page += 1) {
    const response = await listFn({ cursor, limit });
    all.push(...response.items);
    if (response.next_cursor === null) break;
    cursor = response.next_cursor;
  }
  return all;
}

/**
 * Full client-side scan + filter of `subscripciones-cliente` for one
 * cliente, capped at `maxPages * limit` (default 10 x 200 = 2000) rows
 * total. Shared by `ClienteVehiculosTab.tsx` and
 * `ClienteSuscripciones.tsx` so the pagination/filter logic lives in
 * exactly one place.
 */
export async function listSubscripcionesClienteByCliente(
  uuidCliente: string,
  opts: { maxPages?: number; limit?: number } = {},
): Promise<SubscripcionCliente[]> {
  const all = await fetchAllPages((p) => listSubscripcionesCliente(p), opts);
  return all.filter((row) => row.uuid_cliente === uuidCliente);
}

/** Same cap/limitation as above, filtered by a set of `uuid_subscripcion_cliente`. */
export async function listSubscripcionVehiculosByIds(
  subscripcionUuids: ReadonlySet<string>,
  opts: { maxPages?: number; limit?: number } = {},
): Promise<SubscripcionVehiculo[]> {
  if (subscripcionUuids.size === 0) return [];
  const all = await fetchAllPages((p) => listSubscripcionVehiculos(p), opts);
  return all.filter(
    (row) => row.uuid_subscripcion_cliente !== null && subscripcionUuids.has(row.uuid_subscripcion_cliente),
  );
}

/** Same cap/limitation as above, filtered by a set of vehiculo `uuid`s. */
export async function listVehiculosByIds(
  vehiculoUuids: ReadonlySet<string>,
  opts: { maxPages?: number; limit?: number } = {},
): Promise<Vehiculo[]> {
  if (vehiculoUuids.size === 0) return [];
  const all = await fetchAllPages((p) => listVehiculos(p), opts);
  return all.filter((row) => vehiculoUuids.has(row.uuid));
}
