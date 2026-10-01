/**
 * `resolucionFacturacionApi.ts` — HTTP client for the HU-F15.3
 * "Resoluciones" tab.
 *
 * Endpoints consumed (see `backend/.../api/v1/empresa.py`,
 * `_resolucion_dedicated_router` / factory mount for
 * `"resolucion-facturacion"`). ALL of them are DIAN-root / cloud-only
 * (REQ-X3, admin- issuer only) — mounted on `api_admin` ONLY; a branch
 * deploy (`api_sucursal`) 404s every one of these routes (see
 * `api/v1/__init__.py::_CLOUD_ONLY_EMPRESA_RESOURCES`):
 *
 * - `GET  /api/v1/empresa/resolucion-facturacion?vigente_en=...&cursor=...&limit=...`
 * - `POST /api/v1/empresa/resolucion-facturacion`
 * - `PUT  /api/v1/empresa/resolucion-facturacion/{uuid}`
 * - `GET  /api/v1/empresa/resolucion-facturacion/{uuid}/consecutivo-actual`
 *
 * The list endpoint does NOT filter by `uuid_sucursal` server-side on this
 * dedicated path (same drift already documented in
 * `parametrizacionEfectivaApi.ts`) — client-side filtering by branch lives
 * in `../hooks/useResolucionesSucursal.ts`, not here.
 */
import { parkosFetchRaw, type ParkosFetchInit } from '@parkos/ui-kit/fetch';

import {
  resolucionFacturacionConsecutivoActualSchema,
  resolucionFacturacionCreateSchema,
  resolucionFacturacionReadListEnvelopeSchema,
  resolucionFacturacionReadSchema,
  resolucionFacturacionUpdateSchema,
  resolucionFacturacionValidationErrorSchema,
  type ResolucionFacturacion,
  type ResolucionFacturacionConsecutivoActual,
  type ResolucionFacturacionCreateInput,
  type ResolucionFacturacionUpdateInput,
} from './resolucionFacturacionSchema';

export type {
  ResolucionFacturacion,
  ResolucionFacturacionConsecutivoActual,
  ResolucionFacturacionCreateInput,
  ResolucionFacturacionUpdateInput,
};

const jsonHeaders = {
  Accept: 'application/json',
  'Content-Type': 'application/json',
};

const getHeaders = {
  Accept: 'application/json',
};

/**
 * Translate a 422 response body into `ResolucionFacturacionVigenciaError`.
 * The backend's `fecha_fin_vigencia > fecha_inicio_vigencia` guard is a
 * plain pydantic `model_validator`, so FastAPI reports it through its
 * STANDARD `{"detail": [...]}` validation envelope (no bespoke typed shape
 * like `tarifa_overlap`) — this class exists so the form layer can
 * `instanceof` it without re-parsing that envelope itself.
 */
export class ResolucionFacturacionVigenciaError extends Error {
  constructor(body: unknown) {
    const parsed = resolucionFacturacionValidationErrorSchema.safeParse(body);
    const issue = parsed.success
      ? parsed.data.detail.find((d) => d.msg.includes('fecha_fin_vigencia'))
      : undefined;
    super(
      issue?.msg.replace(/^Value error,\s*/, '')
        ?? 'fecha_fin_vigencia debe ser posterior a fecha_inicio_vigencia',
    );
    this.name = 'ResolucionFacturacionVigenciaError';
  }
}

function throwTypedError(res: Response, bodyText: string): never {
  if (res.status === 422) {
    let parsedBody: unknown;
    try {
      parsedBody = JSON.parse(bodyText);
    } catch {
      throw new Error(`resolucionFacturacionApi: 422 ${bodyText.slice(0, 200)}`);
    }
    throw new ResolucionFacturacionVigenciaError(parsedBody);
  }
  throw new Error(`resolucionFacturacionApi: ${res.status}: ${bodyText.slice(0, 200)}`);
}

async function fetchJsonOrTyped(input: string, init: ParkosFetchInit): Promise<unknown> {
  const res = await parkosFetchRaw(input, init);
  if (!res.ok) {
    const body = await res.text();
    throwTypedError(res, body);
  }
  return (await res.json()) as unknown;
}

export interface ListResolucionesFacturacionOpts {
  vigenteEn?: string;
  cursor?: string;
  limit?: number;
}

export interface ResolucionesFacturacionPage {
  items: ResolucionFacturacion[];
  nextCursor: string | null;
}

/**
 * `GET /api/v1/empresa/resolucion-facturacion`. Cloud-only (DIAN root,
 * REQ-X3): on a branch deploy this route is absent entirely, so the
 * request 404s. Mirrors `parametrizacionEfectivaApi.ts::countVigentes`'s
 * convention — a 404 here means "zero rows", not an error, since the
 * caller (`useResolucionesSucursal.ts`) needs an empty-list UI, not a
 * hard failure, when a branch deploy has no DIAN root mounted.
 */
export async function listResolucionesFacturacion(
  opts: ListResolucionesFacturacionOpts = {},
): Promise<ResolucionesFacturacionPage> {
  const params = new URLSearchParams();
  if (opts.vigenteEn !== undefined) params.set('vigente_en', opts.vigenteEn);
  if (opts.cursor !== undefined) params.set('cursor', opts.cursor);
  if (opts.limit !== undefined) params.set('limit', String(opts.limit));
  const qs = params.toString();
  const url = `/api/v1/empresa/resolucion-facturacion${qs ? `?${qs}` : ''}`;

  const res = await parkosFetchRaw(url, { method: 'GET', headers: getHeaders });
  if (!res.ok) {
    if (res.status === 404) return { items: [], nextCursor: null };
    const body = await res.text();
    throw new Error(
      `resolucionFacturacionApi: GET ${url} -> ${res.status}: ${body.slice(0, 200)}`,
    );
  }
  const raw = (await res.json()) as unknown;
  const parsed = resolucionFacturacionReadListEnvelopeSchema.parse(raw);
  return { items: parsed.items, nextCursor: parsed.next_cursor ?? null };
}

export async function createResolucionFacturacion(
  input: ResolucionFacturacionCreateInput,
): Promise<ResolucionFacturacion> {
  const parsed = resolucionFacturacionCreateSchema.parse(input);
  const raw = await fetchJsonOrTyped('/api/v1/empresa/resolucion-facturacion', {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify(parsed),
  });
  return resolucionFacturacionReadSchema.parse(raw);
}

export async function updateResolucionFacturacion(
  uuid: string,
  input: ResolucionFacturacionUpdateInput,
): Promise<ResolucionFacturacion> {
  const parsed = resolucionFacturacionUpdateSchema.parse(input);
  const raw = await fetchJsonOrTyped(`/api/v1/empresa/resolucion-facturacion/${uuid}`, {
    method: 'PUT',
    headers: jsonHeaders,
    body: JSON.stringify(parsed),
  });
  return resolucionFacturacionReadSchema.parse(raw);
}

/**
 * `GET /api/v1/empresa/resolucion-facturacion/{uuid}/consecutivo-actual`.
 *
 * Returns `null` instead of throwing on a 404 (`resolucion_no_encontrada`).
 * This is deliberately lenient: the caller (`ResolucionesDIAN.tsx`) queries
 * this for every vigente row right after the list loads (or a fresh create
 * completes), and the banner it feeds is informational-only (BR2
 * "agotandose" warning) — a transient miss (e.g. the row not being visible
 * yet to a read replica, or the caller racing a stale uuid from a
 * just-replaced list) should degrade to "no banner" rather than surface a
 * hard error for what is, from the operator's perspective, still a
 * perfectly valid screen.
 */
export async function getConsecutivoActual(
  uuid: string,
): Promise<ResolucionFacturacionConsecutivoActual | null> {
  const res = await parkosFetchRaw(
    `/api/v1/empresa/resolucion-facturacion/${uuid}/consecutivo-actual`,
    { method: 'GET', headers: getHeaders },
  );
  if (!res.ok) {
    if (res.status === 404) return null;
    const body = await res.text();
    throw new Error(
      `resolucionFacturacionApi: GET consecutivo-actual -> ${res.status}: ${body.slice(0, 200)}`,
    );
  }
  const raw = (await res.json()) as unknown;
  return resolucionFacturacionConsecutivoActualSchema.parse(raw);
}
