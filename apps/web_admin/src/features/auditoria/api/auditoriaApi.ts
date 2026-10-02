/**
 * `auditoriaApi.ts` — HTTP client for the HU-F20.4 admin "bitácora"
 * surface, consuming the 3 real endpoints
 * (`backend/.../api/v1/auditoria.py`, already merged into this same
 * worktree):
 *
 *   - GET /api/v1/admin/log-transaccional?tabla=&uuid_registro=&uuid_sucursal=&uuid_usuario=&desde=&hasta=&cursor=&limit=
 *   - GET /api/v1/admin/log-transaccional/verify-chain?tabla=&uuid_sucursal=
 *   - GET /api/v1/admin/log-transaccional/buscar?prefijo=&limit=
 *
 * Thin transport only, same convention as `syncApi.ts` / `alertasApi.ts`:
 * build the URL, fetch, parse with Zod. SWR / trigger-hook logic lives in
 * `hooks/*.ts`.
 */
import { parkosFetchRaw, type ParkosFetchInit } from '@/lib/fetch';

import {
  auditLogListResponseSchema,
  verifyChainResponseSchema,
  buscarPrefijoResponseSchema,
  type AuditLogListResponse,
  type VerifyChainResponse,
  type BuscarPrefijoResponse,
  type LogTransaccionalListQuery,
  type VerifyChainQuery,
  type BuscarPrefijoQuery,
} from './auditoriaSchema';

const LIST_PATH = '/api/v1/admin/log-transaccional';
const VERIFY_CHAIN_PATH = `${LIST_PATH}/verify-chain`;
const BUSCAR_PATH = `${LIST_PATH}/buscar`;

/** 422 `rango_fecha_invalido` -- `desde` > `hasta`. */
export class AuditRangoFechaInvalidoError extends Error {
  constructor() {
    super('El rango de fechas es inválido: "Desde" no puede ser posterior a "Hasta".');
    this.name = 'AuditRangoFechaInvalidoError';
  }
}

/** 403 `unauthorized_sucursal_context` -- `uuid_sucursal` not in the actor's permitted branches. */
export class AuditUnauthorizedSucursalError extends Error {
  constructor() {
    super('No tenés acceso a esa sucursal.');
    this.name = 'AuditUnauthorizedSucursalError';
  }
}

/** 400 `missing_sucursal_context` -- the actor has zero permitted branches. */
export class AuditMissingSucursalContextError extends Error {
  constructor() {
    super('No hay sucursales permitidas para este administrador.');
    this.name = 'AuditMissingSucursalContextError';
  }
}

/** 400 `invalid_cursor` -- malformed/stale pagination cursor. */
export class AuditInvalidCursorError extends Error {
  constructor(detail?: string) {
    super(`El cursor de paginación no es válido${detail ? `: ${detail}` : '.'}`);
    this.name = 'AuditInvalidCursorError';
  }
}

/** 422 `tabla_no_verificable` -- `tabla` has no hash-chain to verify. */
export class AuditTablaNoVerificableError extends Error {
  constructor(tabla: string) {
    super(`La tabla "${tabla}" no tiene cadena de hashes verificable.`);
    this.name = 'AuditTablaNoVerificableError';
  }
}

/** `{"detail": {"error": <code>, ...}}` -- this repo's HTTPException-detail convention (mirrors `alertasApi.ts::detailOf`). */
function errorDetailOf(bodyText: string): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(bodyText) as unknown;
    if (typeof parsed === 'object' && parsed !== null && 'detail' in parsed) {
      const detail = (parsed as { detail?: unknown }).detail;
      if (typeof detail === 'object' && detail !== null) {
        return detail as Record<string, unknown>;
      }
    }
  } catch {
    // Not JSON (or shape mismatch) -- callers fall back to a static message.
  }
  return null;
}

function errorCodeOf(bodyText: string): string | null {
  const code = errorDetailOf(bodyText)?.error;
  return typeof code === 'string' ? code : null;
}

/**
 * Maps the 5 documented error codes shared across the list + verify-chain
 * endpoints to typed errors; anything else falls back to a generic Error
 * carrying the raw status + truncated body (same shape as `syncApi.ts` /
 * `alertasApi.ts`'s fallback).
 */
async function throwAuditError(res: Response, input: string, method: string): Promise<never> {
  const bodyText = await res.text();
  const code = errorCodeOf(bodyText);

  if (res.status === 422 && code === 'rango_fecha_invalido') {
    throw new AuditRangoFechaInvalidoError();
  }
  if (res.status === 422 && code === 'tabla_no_verificable') {
    const detail = errorDetailOf(bodyText)?.detail;
    throw new AuditTablaNoVerificableError(typeof detail === 'string' ? detail : '');
  }
  if (res.status === 403 && code === 'unauthorized_sucursal_context') {
    throw new AuditUnauthorizedSucursalError();
  }
  if (res.status === 400 && code === 'missing_sucursal_context') {
    throw new AuditMissingSucursalContextError();
  }
  if (res.status === 400 && code === 'invalid_cursor') {
    const detail = errorDetailOf(bodyText)?.detail;
    throw new AuditInvalidCursorError(typeof detail === 'string' ? detail : undefined);
  }
  throw new Error(`auditoriaApi: ${method} ${input} -> ${res.status}: ${bodyText.slice(0, 200)}`);
}

export async function fetchLogTransaccional(
  query: LogTransaccionalListQuery,
): Promise<AuditLogListResponse> {
  const params = new URLSearchParams();
  if (query.tabla) params.set('tabla', query.tabla);
  if (query.uuid_registro) params.set('uuid_registro', query.uuid_registro);
  if (query.uuid_sucursal) params.set('uuid_sucursal', query.uuid_sucursal);
  if (query.uuid_usuario) params.set('uuid_usuario', query.uuid_usuario);
  if (query.desde) params.set('desde', query.desde);
  if (query.hasta) params.set('hasta', query.hasta);
  if (query.cursor) params.set('cursor', query.cursor);
  params.set('limit', String(query.limit ?? 20));

  const url = `${LIST_PATH}?${params.toString()}`;
  const init: ParkosFetchInit = { method: 'GET', headers: { Accept: 'application/json' } };
  const res = await parkosFetchRaw(url, init);
  if (res.ok) {
    return auditLogListResponseSchema.parse(await res.json());
  }
  return throwAuditError(res, url, 'GET');
}

export async function fetchVerifyChain(query: VerifyChainQuery): Promise<VerifyChainResponse> {
  const params = new URLSearchParams();
  params.set('tabla', query.tabla ?? 'log_transaccional');
  if (query.uuid_sucursal) params.set('uuid_sucursal', query.uuid_sucursal);

  const url = `${VERIFY_CHAIN_PATH}?${params.toString()}`;
  const init: ParkosFetchInit = { method: 'GET', headers: { Accept: 'application/json' } };
  const res = await parkosFetchRaw(url, init);
  if (res.ok) {
    return verifyChainResponseSchema.parse(await res.json());
  }
  return throwAuditError(res, url, 'GET');
}

export async function buscarLogTransaccional(
  query: BuscarPrefijoQuery,
): Promise<BuscarPrefijoResponse> {
  const params = new URLSearchParams();
  params.set('prefijo', query.prefijo);
  params.set('limit', String(query.limit ?? 10));

  const url = `${BUSCAR_PATH}?${params.toString()}`;
  const init: ParkosFetchInit = { method: 'GET', headers: { Accept: 'application/json' } };
  const res = await parkosFetchRaw(url, init);
  if (res.ok) {
    return buscarPrefijoResponseSchema.parse(await res.json());
  }
  return throwAuditError(res, url, 'GET');
}
