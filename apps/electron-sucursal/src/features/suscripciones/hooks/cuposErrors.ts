/**
 * `cuposErrors.ts` — typed error subclasses for the HU-F9.2 realineada
 * cupos-management backend error codes (`clientes_cupos.py`).
 *
 * Mirrors `ventaSuscripcionErrors.ts` precedent verbatim: pure typed
 * JS errors (NOT extending `ParkosHttpError`) with a `status` field,
 * so the cupos UI can `instanceof`-discriminate the inline message
 * independently of the HTTP transport layer.
 */

/** 404 `subscripcion_no_encontrada` — the target subscripcion isn't active at this branch. */
export class CuposSubscripcionNoEncontradaError extends Error {
  public readonly status = 404;
  constructor() {
    super('subscripcion_no_encontrada');
    this.name = 'CuposSubscripcionNoEncontradaError';
  }
}

/** 409 `vehiculo_ya_inscrito` — the placa is already enrolled (vigente) in this subscripcion. */
export class CuposVehiculoYaInscritoError extends Error {
  public readonly status = 409;
  public readonly placa: string;
  constructor(placa: string) {
    super('vehiculo_ya_inscrito');
    this.name = 'CuposVehiculoYaInscritoError';
    this.placa = placa;
  }
}

/** 422 `tipo_vehiculo_incompatible` — plan.mismo_tipo_vehiculo=true but tipos differ. */
export class CuposTipoIncompatibleError extends Error {
  public readonly status = 422;
  public readonly tipos_encontrados: string[];
  constructor(tipos_encontrados: string[]) {
    super('tipo_vehiculo_incompatible');
    this.name = 'CuposTipoIncompatibleError';
    this.tipos_encontrados = tipos_encontrados;
  }
}

/** 422 `cantidad_maxima_excedida` — cupo already full. */
export class CuposCantidadMaximaError extends Error {
  public readonly status = 422;
  public readonly max: number;
  constructor(max: number) {
    super('cantidad_maxima_excedida');
    this.name = 'CuposCantidadMaximaError';
    this.max = max;
  }
}

/** 404 `vehiculo_inscrito_no_encontrado` — "quitar" target doesn't match an active row. */
export class CuposVehiculoInscritoNoEncontradoError extends Error {
  public readonly status = 404;
  constructor() {
    super('vehiculo_inscrito_no_encontrado');
    this.name = 'CuposVehiculoInscritoNoEncontradoError';
  }
}

/** 403 `permission_denied` — only the supervisor profile manages plates (PT-2). */
export class CuposPermisoDenegadoError extends Error {
  public readonly status = 403;
  constructor() {
    super('permission_denied');
    this.name = 'CuposPermisoDenegadoError';
  }
}

/**
 * 400 `missing_sucursal_context` / 403 `unauthorized_sucursal_context` —
 * the supervisor token reached the branch API without a valid
 * `X-Sucursal-Context` (PT-2).
 */
export class CuposContextoSucursalError extends Error {
  public readonly status: number;
  constructor(status: number, code: string) {
    super(code);
    this.name = 'CuposContextoSucursalError';
    this.status = status;
  }
}

/** 409 `placa_con_suscripcion_activa` — the plate belongs to another active subscription of this branch. */
export class CuposPlacaConSuscripcionActivaError extends Error {
  public readonly status = 409;
  public readonly placa: string;
  public readonly uuid_subscripcion_cliente: string | null;
  constructor(placa: string, uuid_subscripcion_cliente: string | null) {
    super('placa_con_suscripcion_activa');
    this.name = 'CuposPlacaConSuscripcionActivaError';
    this.placa = placa;
    this.uuid_subscripcion_cliente = uuid_subscripcion_cliente;
  }
}

/** 422 `tipo_vehiculo_plan_incompatible` — the vehicle type does not match the plan's type. */
export class CuposTipoPlanIncompatibleError extends Error {
  public readonly status = 422;
  public readonly tipo_plan: string | null;
  public readonly tipos_encontrados: string[];
  constructor(tipo_plan: string | null, tipos_encontrados: string[]) {
    super('tipo_vehiculo_plan_incompatible');
    this.name = 'CuposTipoPlanIncompatibleError';
    this.tipo_plan = tipo_plan;
    this.tipos_encontrados = tipos_encontrados;
  }
}

/** Backend `detail` payload shared by the add/remove plate endpoints. */
export interface CuposBackendErrorBody {
  error?: string;
  placa?: string;
  uuid_subscripcion_cliente?: string;
  tipo_plan?: string;
  tipos_encontrados?: string[];
  cantidad_maxima_vehiculos?: number;
}

/**
 * FastAPI serializes `HTTPException(detail={"error": ...})` as
 * `{"detail": {"error": ...}}`; falls back to the top-level object.
 */
export function parseCuposBackendBody(body: string): CuposBackendErrorBody | null {
  try {
    const parsed = JSON.parse(body) as { detail?: unknown } & CuposBackendErrorBody;
    const detail = parsed.detail;
    if (detail && typeof detail === 'object') return detail as CuposBackendErrorBody;
    return parsed;
  } catch {
    return null;
  }
}

/**
 * Maps an HTTP status + backend body of the add/remove plate endpoints to
 * its typed error (PT-2 contract). `null` when the pair is not a known
 * business error (caller rethrows the original transport error).
 */
export function mapCuposHttpError(
  status: number,
  body: string,
  fallbackPlaca = '',
): Error | null {
  const parsed = parseCuposBackendBody(body);
  const code = parsed?.error;
  if (!code) return null;
  if (status === 403 && code === 'permission_denied') return new CuposPermisoDenegadoError();
  if (
    (status === 400 && code === 'missing_sucursal_context') ||
    (status === 403 && code === 'unauthorized_sucursal_context')
  ) {
    return new CuposContextoSucursalError(status, code);
  }
  if (status === 404 && code === 'subscripcion_no_encontrada') {
    return new CuposSubscripcionNoEncontradaError();
  }
  if (status === 404 && code === 'vehiculo_inscrito_no_encontrado') {
    return new CuposVehiculoInscritoNoEncontradoError();
  }
  if (status === 409 && code === 'vehiculo_ya_inscrito') {
    return new CuposVehiculoYaInscritoError(parsed?.placa ?? fallbackPlaca);
  }
  if (status === 409 && code === 'placa_con_suscripcion_activa') {
    return new CuposPlacaConSuscripcionActivaError(
      parsed?.placa ?? fallbackPlaca,
      parsed?.uuid_subscripcion_cliente ?? null,
    );
  }
  if (status === 422 && code === 'tipo_vehiculo_plan_incompatible') {
    return new CuposTipoPlanIncompatibleError(
      parsed?.tipo_plan ?? null,
      parsed?.tipos_encontrados ?? [],
    );
  }
  if (status === 422 && code === 'tipo_vehiculo_incompatible') {
    return new CuposTipoIncompatibleError(parsed?.tipos_encontrados ?? []);
  }
  if (status === 422 && code === 'cantidad_maxima_excedida') {
    return new CuposCantidadMaximaError(parsed?.cantidad_maxima_vehiculos ?? 0);
  }
  return null;
}
