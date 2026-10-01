/**
 * `cuposApi.ts` — HTTP client for the admin Cupo (cantidad-vehiculos-
 * sucursal) CRUD UI (PR-D).
 *
 * Endpoints consumed:
 * - `GET    /api/v1/empresa/cantidad-vehiculos-sucursal?limit=…`
 * - `GET    /api/v1/empresa/cantidad-vehiculos-sucursal/by-key?…`
 * - `GET    /api/v1/empresa/cantidad-vehiculos-sucursal/{uuid}`
 * - `POST   /api/v1/empresa/cantidad-vehiculos-sucursal`
 * - `PUT    /api/v1/empresa/cantidad-vehiculos-sucursal/{uuid}`
 *
 * Three typed errors surfaced from the backend:
 *   - ``CantidadOverlapError`` (409 ``cantidad_overlap``)
 *   - ``CantidadBajoIngresosError`` (422 ``capacidad_insuficiente``, BR2 HU-F14.4)
 *   - ``CantidadSucursalInmutableError`` (422 ``sucursal_inmutable``)
 *
 * The form layer uses ``instanceof`` to render an operator-readable
 * message ("hay 8 ingresos activos, no podés bajar a 5") instead of a
 * generic 409/422 toast.
 */
import { parkosFetchRaw, type ParkosFetchInit } from '@parkos/ui-kit/fetch';

import {
  cupoBajoIngresosErrorSchema,
  cupoCreateSchema,
  cupoOverlapErrorSchema,
  cupoReadListEnvelopeSchema,
  cupoReadSchema,
  cupoSucursalInmutableErrorSchema,
  cupoUpdateSchema,
  type Cupo,
  type CupoCreateInput,
  type CupoUpdateInput,
} from './cupoSchema';

export type { Cupo, CupoCreateInput, CupoUpdateInput };

const jsonHeaders = {
  Accept: 'application/json',
  'Content-Type': 'application/json',
};

async function fetchJson<T>(input: string, init: ParkosFetchInit): Promise<T> {
  const res = await parkosFetchRaw(input, init);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(
      `cuposApi: ${init.method ?? 'GET'} ${input} -> ${res.status}: ${body.slice(0, 200)}`,
    );
  }
  return (await res.json()) as T;
}

export class CantidadOverlapError extends Error {
  readonly conflictingUuid: string;
  readonly conflictingVigenteDesde: string | null;
  readonly conflictingVigenteHasta: string | null;

  constructor(body: unknown) {
    const parsed = cupoOverlapErrorSchema.safeParse(body);
    if (!parsed.success) {
      super('Solapamiento con un cupo existente (UUID no disponible)');
      this.name = 'CantidadOverlapError';
      this.conflictingUuid = '';
      this.conflictingVigenteDesde = null;
      this.conflictingVigenteHasta = null;
      return;
    }
    super(
      `La nueva ventana se solapa con el cupo ${parsed.data.detail.conflicting_uuid}`,
    );
    this.name = 'CantidadOverlapError';
    this.conflictingUuid = parsed.data.detail.conflicting_uuid;
    this.conflictingVigenteDesde = parsed.data.detail.conflicting_vigente_desde;
    this.conflictingVigenteHasta = parsed.data.detail.conflicting_vigente_hasta;
  }
}

export class CantidadBajoIngresosError extends Error {
  readonly tipo: string | null;
  readonly ocupadoActual: number;
  readonly solicitado: number;

  constructor(body: unknown) {
    const parsed = cupoBajoIngresosErrorSchema.safeParse(body);
    if (!parsed.success) {
      super('Capacidad insuficiente (detalle no disponible)');
      this.name = 'CantidadBajoIngresosError';
      this.tipo = null;
      this.ocupadoActual = 0;
      this.solicitado = 0;
      return;
    }
    super(
      `Hay ${parsed.data.detail.ocupado_actual} vehículo(s) ocupando el tipo ${parsed.data.detail.tipo ?? '?'}; no podés bajar el cupo a ${parsed.data.detail.solicitado}. Cerrá o anulá los ingresos primero.`,
    );
    this.name = 'CantidadBajoIngresosError';
    this.tipo = parsed.data.detail.tipo;
    this.ocupadoActual = parsed.data.detail.ocupado_actual;
    this.solicitado = parsed.data.detail.solicitado;
  }
}

export class CantidadSucursalInmutableError extends Error {
  readonly uuid: string;
  readonly existingSucursal: string;
  readonly attemptedSucursal: string;

  constructor(body: unknown) {
    const parsed = cupoSucursalInmutableErrorSchema.safeParse(body);
    if (!parsed.success) {
      super('La sucursal del cupo no puede cambiarse');
      this.name = 'CantidadSucursalInmutableError';
      this.uuid = '';
      this.existingSucursal = '';
      this.attemptedSucursal = '';
      return;
    }
    super(
      `El cupo pertenece a la sucursal ${parsed.data.detail.existing_sucursal}; no se puede mover a ${parsed.data.detail.attempted_sucursal}`,
    );
    this.name = 'CantidadSucursalInmutableError';
    this.uuid = parsed.data.detail.uuid;
    this.existingSucursal = parsed.data.detail.existing_sucursal;
    this.attemptedSucursal = parsed.data.detail.attempted_sucursal;
  }
}

function throwTypedError(res: Response, bodyText: string): never {
  if (res.status === 409) {
    try {
      throw new CantidadOverlapError(JSON.parse(bodyText));
    } catch {
      throw new Error(`cuposApi: 409 ${bodyText.slice(0, 200)}`);
    }
  }
  if (res.status === 422) {
    let parsedBody: unknown;
    try {
      parsedBody = JSON.parse(bodyText);
    } catch {
      throw new Error(`cuposApi: 422 ${bodyText.slice(0, 200)}`);
    }
    const bajo = cupoBajoIngresosErrorSchema.safeParse(parsedBody);
    if (bajo.success) {
      throw new CantidadBajoIngresosError(parsedBody);
    }
    try {
      throw new CantidadSucursalInmutableError(parsedBody);
    } catch {
      throw new Error(`cuposApi: 422 ${bodyText.slice(0, 200)}`);
    }
  }
  throw new Error(`cuposApi: ${res.status}: ${bodyText.slice(0, 200)}`);
}

async function fetchJsonOrTyped(input: string, init: ParkosFetchInit): Promise<unknown> {
  const res = await parkosFetchRaw(input, init);
  if (!res.ok) {
    const body = await res.text();
    throwTypedError(res, body);
  }
  return (await res.json()) as unknown;
}

export interface ListCuposOpts {
  limit?: number;
}

export async function listCupos(opts: ListCuposOpts = {}): Promise<Cupo[]> {
  const params = new URLSearchParams();
  if (opts.limit !== undefined) params.set('limit', String(opts.limit));
  const qs = params.toString();
  const url = `/api/v1/empresa/cantidad-vehiculos-sucursal${qs ? `?${qs}` : ''}`;
  const raw = await fetchJson<unknown>(url, { method: 'GET', headers: jsonHeaders });
  return cupoReadListEnvelopeSchema.parse(raw).items;
}

export interface ByKeyCuposOpts {
  sucursal: string;
  tipo_vehiculo?: string | null;
}

export async function listCuposByKey(opts: ByKeyCuposOpts): Promise<Cupo[]> {
  const params = new URLSearchParams({ sucursal: opts.sucursal });
  if (opts.tipo_vehiculo !== undefined && opts.tipo_vehiculo !== null) {
    params.set('tipo_vehiculo', opts.tipo_vehiculo);
  }
  const url = `/api/v1/empresa/cantidad-vehiculos-sucursal/by-key?${params.toString()}`;
  const raw = await fetchJson<unknown>(url, { method: 'GET', headers: jsonHeaders });
  return cupoReadListEnvelopeSchema.parse(raw).items;
}

export async function getCupo(uuid: string): Promise<Cupo> {
  const raw = await fetchJsonOrTyped(`/api/v1/empresa/cantidad-vehiculos-sucursal/${uuid}`, {
    method: 'GET',
    headers: jsonHeaders,
  });
  return cupoReadSchema.parse(raw);
}

export async function createCupo(input: CupoCreateInput): Promise<Cupo> {
  const parsed = cupoCreateSchema.parse(input);
  const raw = await fetchJsonOrTyped('/api/v1/empresa/cantidad-vehiculos-sucursal', {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify(parsed),
  });
  return cupoReadSchema.parse(raw);
}

export async function updateCupo(
  uuid: string,
  input: CupoUpdateInput,
): Promise<Cupo> {
  const parsed = cupoUpdateSchema.parse(input);
  const raw = await fetchJsonOrTyped(
    `/api/v1/empresa/cantidad-vehiculos-sucursal/${uuid}`,
    {
      method: 'PUT',
      headers: jsonHeaders,
      body: JSON.stringify(parsed),
    },
  );
  return cupoReadSchema.parse(raw);
}
