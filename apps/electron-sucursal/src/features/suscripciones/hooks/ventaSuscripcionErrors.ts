/**
 * `ventaSuscripcionErrors.ts` — typed error subclasses for the 3
 * backend 422 codes that REQ-OPS-179 surfaces inline in wizard
 * step 2 (HU-F9.1).
 *
 * Mirrors F7.2 `SalidaDuplicadaError` precedent verbatim: each
 * class carries the backend's status code + the discriminated
 * payload field, and the wizard step 2 uses `instanceof` to render
 * the inline message.
 *
 * The backend F1.12 typed-error bodies live at
 * `backend/.../schemas/clientes.py` §9.2:
 *   - `SubscripcionDuplicadaPlacaError` → `{placa}`
 *   - `TipoVehiculoIncompatibleError` → `{tipos_encontrados}`
 *   - `CantidadMaximaExcedidaError` → `{cantidad_maxima_vehiculos}`
 *
 * Note: these classes do NOT extend `ParkosHttpError` — they are
 * pure typed JS errors with a `status` field. The wizard
 * `instanceof` checks are independent of the HTTP transport layer
 * (mirrors F7.2 `SalidaDuplicadaError` which also does NOT extend
 * `ParkosHttpError`).
 */

/**
 * 422 `suscripcion_duplicada_placa` — a placa in `payload.placas`
 * already has an active subscription at this branch (F1.12
 * REQ-OPS-089). Carries the offending placa.
 */
export class VentaSuscripcionDuplicatePlateError extends Error {
  public readonly status = 422;
  public readonly placa: string;
  constructor(placa: string) {
    super('suscripcion_duplicada_placa');
    this.name = 'VentaSuscripcionDuplicatePlateError';
    this.placa = placa;
  }
}

/**
 * 422 `tipo_vehiculo_incompatible` — `plan.mismo_tipo_vehiculo=true`
 * but the placas resolve to distinct `uuid_tipo_vehiculo` (F1.12
 * REQ-OPS-087). Carries the list of distinct tipos found.
 */
export class VentaSuscripcionTipoIncompatibleError extends Error {
  public readonly status = 422;
  public readonly tipos_encontrados: string[];
  constructor(tipos_encontrados: string[]) {
    super('tipo_vehiculo_incompatible');
    this.name = 'VentaSuscripcionTipoIncompatibleError';
    this.tipos_encontrados = tipos_encontrados;
  }
}

/**
 * 422 `cantidad_maxima_excedida` — `len(payload.placas) >
 * plan.cantidad_maxima_vehiculos` (F1.12 REQ-OPS-088). Carries
 * the plan's max-vehiculos limit.
 */
export class VentaSuscripcionCantidadMaximaError extends Error {
  public readonly status = 422;
  public readonly max: number;
  constructor(max: number) {
    super('cantidad_maxima_excedida');
    this.name = 'VentaSuscripcionCantidadMaximaError';
    this.max = max;
  }
}
