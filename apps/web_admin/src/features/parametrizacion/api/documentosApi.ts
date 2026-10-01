/**
 * `documentosApi.ts` — HTTP client for `prod.documentos` (HU-F15.4).
 *
 * Endpoint (confirmed against `backend/.../api/v1/empresa.py:389` +
 * `router_factory.make_router`): `GET/POST/PUT /api/v1/empresa/documentos`.
 * `plan.md:3632` documents the GET as `?uuid_sucursal=X&tipo=`, but that
 * query contract does NOT exist in the real code:
 *
 *   - `DocumentosFilter` (schemas/empresa.py) is declared but never wired
 *     into the generic `list_endpoint` — the factory's list handler only
 *     binds `cursor`/`limit`, nothing else. A `?uuid_sucursal=`/`?tipo=`
 *     on the wire is silently ignored by FastAPI (not bound to any
 *     parameter), it does NOT filter anything server-side.
 *   - The *actual* branch scoping on GET comes from the ambient tenant
 *     listener (`db.tenancy.do_orm_execute`), driven by the
 *     `X-Sucursal-Context` HEADER (auto-injected by `parkosFetch` from
 *     the GLOBAL active branch in the topbar selector, not from this
 *     page's route `:uuid` — see `lib/sucursal-context.tsx`). When no
 *     branch is selected, the header is absent and the list runs in
 *     "global" mode (every branch combined, admin- only).
 *
 * `listDocumentosPorSucursal` works around this by paging the FULL list
 * (bounded by `MAX_PAGES` as a safety cap) and filtering client-side by
 * `uuid_sucursal`, instead of trusting a query param that the backend
 * never binds. `SucursalDocumentos.tsx` additionally refuses to render
 * the management UI at all when the globally active branch differs from
 * the branch being viewed (see that component's docstring) — the
 * ambient-header scoping means a mismatch would silently return the
 * WRONG branch's rows (or none), which client-side filtering alone
 * cannot recover from.
 */
import { parkosFetchRaw, type ParkosFetchInit } from '@parkos/ui-kit/fetch';

import {
  documentoReadListSchema,
  documentoReadSchema,
  documentoUpsertSchema,
  type Documento,
  type DocumentoUpsertInput,
} from './documentosSchema';

export type { Documento, DocumentoUpsertInput };

const jsonHeaders = {
  Accept: 'application/json',
  'Content-Type': 'application/json',
};

const BASE_PATH = '/api/v1/empresa/documentos';

// Safety cap for the pagination loop below: 20 pages * 200 rows/page =
// 4000 rows max ever read. Each branch has at most 4 active documentos
// (one per `DOCUMENTO_TIPOS` entry), so this comfortably covers tenants
// with hundreds of branches without risking an unbounded loop.
const MAX_PAGES = 20;
const PAGE_LIMIT = 200;

async function fetchJson<T>(input: string, init: ParkosFetchInit): Promise<T> {
  const res = await parkosFetchRaw(input, init);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(
      `documentosApi: ${init.method ?? 'GET'} ${input} -> ${res.status}: ${body.slice(0, 200)}`,
    );
  }
  return (await res.json()) as T;
}

/**
 * Lista TODOS los documentos vigentes de UNA sucursal específica.
 *
 * Pagina el listado completo (ver docstring del módulo para por qué no
 * se puede confiar en un query param `uuid_sucursal`) y filtra
 * client-side por `uuid_sucursal === uuidSucursal`.
 */
export async function listDocumentosPorSucursal(uuidSucursal: string): Promise<Documento[]> {
  const collected: Documento[] = [];
  let cursor: string | null = null;

  for (let page = 0; page < MAX_PAGES; page += 1) {
    const params = new URLSearchParams({ limit: String(PAGE_LIMIT) });
    if (cursor) params.set('cursor', cursor);
    const raw = await fetchJson<unknown>(`${BASE_PATH}?${params.toString()}`, {
      method: 'GET',
      headers: jsonHeaders,
    });
    const parsed = documentoReadListSchema.parse(raw);
    collected.push(...parsed.items);
    if (!parsed.next_cursor) break;
    cursor = parsed.next_cursor;
  }

  return collected.filter((d) => d.uuid_sucursal === uuidSucursal);
}

export async function createDocumento(input: DocumentoUpsertInput): Promise<Documento> {
  const parsed = documentoUpsertSchema.parse(input);
  const raw = await fetchJson<unknown>(BASE_PATH, {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify(parsed),
  });
  return documentoReadSchema.parse(raw);
}

export async function updateDocumento(
  uuid: string,
  input: DocumentoUpsertInput,
): Promise<Documento> {
  const parsed = documentoUpsertSchema.parse(input);
  const raw = await fetchJson<unknown>(`${BASE_PATH}/${uuid}`, {
    method: 'PUT',
    headers: jsonHeaders,
    body: JSON.stringify(parsed),
  });
  return documentoReadSchema.parse(raw);
}

/**
 * BR1: "se sube una vez por sucursal" — si ya existe una versión
 * vigente de ese `tipo` (`current`), hace PUT (close+insert bi-temporal
 * sobre esa fila); si no, hace POST. Mantener esta decisión en UN solo
 * lugar evita que dos llamadas descoordinadas creen dos filas activas
 * del mismo tipo para la misma sucursal (la tabla no tiene UK que lo
 * prevenga — ver docstring de `models/V/documentos.py`).
 */
export async function upsertDocumento(
  current: Documento | undefined,
  input: DocumentoUpsertInput,
): Promise<Documento> {
  if (current) return updateDocumento(current.uuid, input);
  return createDocumento(input);
}
