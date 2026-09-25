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
