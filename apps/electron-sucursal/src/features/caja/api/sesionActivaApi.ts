/**
 * `sesionActivaApi.ts` — HTTP layer para sesión de caja activa del operador.
 *
 * F3.3 — T1. Tres wrappers typed:
 *   - `getSesionActiva()` — GET /caja-sesion/sesion/me. 404 → null (operador
 *     sin turno es estado válido, NO error). 200 → SesionRead.
 *   - `abrirSesion()` — POST /caja-sesion/sesiones. 409
 *     `sesion_already_active` (BD-level partial unique index 0023 F1.3) →
 *     `SesionAlreadyActiveError extends ParkosHttpError`.
 *   - `cerrarSesion()` — PUT /caja-sesion/sesion/{uuid}/cerrar. 404
 *     `SessionNotFoundError` per REST semantics (DEC-F3.3-07) →
 *     `SesionAlreadyClosedError`.
 *
 * El wrapper F2.2 parkosFetch añade:
 *   - Authorization Bearer desde authStore (auto).
 *   - Idempotency-Key SHA-256 sobre POST /caja-sesion/* (skip solo /auth/login).
 *   - 401 retry-once via Mutex `refreshAccessToken()` + clear + parkos:auth:cleared.
 *   - 5xx/408 retry hasta 3 con backoff 300/600/1200ms.
 *
 * Defense in depth XR6 (operational):
 *   - layer 4 contract — frontend typed errors + Zod (T2 schema) + backend
 *     Pydantic + partial unique index 0023.
 *   - layer 5 retry — parkosFetch retry + 401 refresh-once (F2.2 invariant).
 */
import { ParkosHttpError, parkosFetch } from '@parkos/ui-kit/fetch';

/** Path GET sesión activa del operador autenticado (HU-F1.13 shipped). */
const SESION_ME_PATH = '/api/v1/caja-sesion/sesion/me';
/** Path POST apertura sesión (HU-F1.3 shipped). */
const SESIONES_PATH = '/api/v1/caja-sesion/sesiones';
/** Path PUT cierre sesión (HU-F1.13 shipped). */
function sesionCerrarPath(uuid: string): string {
  return `/api/v1/caja-sesion/sesion/${uuid}/cerrar`;
}

/** Cuerpo y respuesta GET /caja-sesion/sesion/me (F1.13 backend Pydantic). */
export interface SesionRead {
  uuid: string;
  uuid_sucursal: string;
  uuid_usuario: string;
  valor_inicial_efectivo: number;
  valor_inicial_datafono: number;
  timestamp_apertura: string;
  timestamp_cierre: string | null;
  observaciones?: string | null;
}

/** Cuerpo POST /caja-sesion/sesiones (F1.3 backend Pydantic). */
export interface SesionCreate {
  uuid_sucursal: string;
  uuid_usuario: string;
  valor_inicial_efectivo: number;
  valor_inicial_datafono: number;
  observaciones?: string;
}

/** Cuerpo PUT /caja-sesion/sesion/{uuid}/cerrar (F1.13 backend Pydantic). */
export interface SesionCerrarRequest {
  valor_final_efectivo: number;
  valor_final_datafono: number;
  observaciones_cierre?: string;
}

/**
 * 409 `sesion_already_active` (DEC-F3.3-08).
 * Proviene del partial unique index `prod.uq_prod_sesion_one_active_per_user`
 * (migration 0023 F1.3). Mapeo UX en `<AbrirTurno>` → "ya tenés un turno abierto".
 */
export class SesionAlreadyActiveError extends ParkosHttpError {
  override readonly name = 'SesionAlreadyActiveError';
  readonly code = 'sesion_already_active' as const;
}

/**
 * 404 `sesion_not_found` per REST semantics (DEC-F3.3-07).
 * Proviene de `SessionNotFoundError` en backend `session_cycle.py:351-352`.
 * Mapeo UX en `<CerrarTurno>` → "esta sesión ya está cerrada" + redirect login.
 */
export class SesionAlreadyClosedError extends ParkosHttpError {
  override readonly name = 'SesionAlreadyClosedError';
  readonly code = 'sesion_not_found' as const;
}

/**
 * GET /caja-sesion/sesion/me — operador autenticado.
 * 404 (sin sesión activa) retorna `null` en vez de throw.
 * Cualquier otro status no-2xx propaga `ParkosHttpError` (5xx reintenta via
 * parkosFetch; 401 refresh-once vía Mutex F2.2 invariant).
 */
export async function getSesionActiva(): Promise<SesionRead | null> {
  try {
    return await parkosFetch<SesionRead>(SESION_ME_PATH);
  } catch (err) {
    if (err instanceof ParkosHttpError && err.status === 404) {
      return null;
    }
    throw err;
  }
}

/**
 * POST /caja-sesion/sesiones — apertura de turno.
 * Backend mapea 23505 (unique violation) → 409 `sesion_already_active`.
 * Cualquier otro error (401, 5xx, network) propaga intacto.
 */
export async function abrirSesion(payload: SesionCreate): Promise<SesionRead> {
  try {
    return await parkosFetch<SesionRead>(SESIONES_PATH, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  } catch (err) {
    if (err instanceof ParkosHttpError && err.status === 409) {
      throw new SesionAlreadyActiveError(err.status, err.body, err.url);
    }
    throw err;
  }
}

/**
 * PUT /caja-sesion/sesion/{uuid}/cerrar — cierre de turno.
 * Backend emite 404 `SessionNotFoundError` cuando ya está cerrada o no existe
 * (DEC-F3.3-07 — REST semantics, NO 409). Otros errores propagan intactos.
 */
export async function cerrarSesion(
  uuid: string,
  payload: SesionCerrarRequest,
): Promise<SesionRead> {
  try {
    return await parkosFetch<SesionRead>(sesionCerrarPath(uuid), {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
  } catch (err) {
    if (err instanceof ParkosHttpError && err.status === 404) {
      throw new SesionAlreadyClosedError(err.status, err.body, err.url);
    }
    throw err;
  }
}