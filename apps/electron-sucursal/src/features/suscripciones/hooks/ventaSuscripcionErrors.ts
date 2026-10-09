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
 * 422 `placa_duplicada_en_venta` — the same placa appears twice in
 * `payload.placas` of one sale (defect 5.4). Carries the repeated placa.
 */
export class VentaSuscripcionPlacaRepetidaError extends Error {
  public readonly status = 422;
  public readonly placa: string;
  constructor(placa: string) {
    super('placa_duplicada_en_venta');
    this.name = 'VentaSuscripcionPlacaRepetidaError';
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

/**
 * 422 sin código tipado (defecto 5.13) — cualquier otra respuesta
 * `422` de la venta: `detail` como string, lista de errores Pydantic
 * (`[{loc, msg}]`) u objeto con un código/mensaje desconocido. Lleva el
 * mensaje legible del servidor para mostrarlo junto al campo de placas;
 * `mensaje` queda vacío si el cuerpo no trae nada utilizable (la UI usa
 * entonces un texto genérico).
 */
export class VentaSuscripcionValidationError extends Error {
  public readonly status = 422;
  public readonly mensaje: string;
  constructor(mensaje: string) {
    super(mensaje || 'venta_suscripcion_422');
    this.name = 'VentaSuscripcionValidationError';
    this.mensaje = mensaje;
  }
}

function nombreCampo(loc: unknown): string {
  if (!Array.isArray(loc)) return '';
  const partes = loc.filter((p) => p !== 'body' && p !== 'query');
  return partes.map(String).join('.');
}

/**
 * Convierte el `detail` de un 422 (FastAPI/Pydantic) a texto legible.
 * Soporta string, lista de errores de validación y objeto (`message`,
 * `msg`, `detail` o el código `error`). Devuelve '' si no hay nada útil.
 */
export function extraerMensajeDetail422(detail: unknown): string {
  if (typeof detail === 'string') return detail.trim();
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === 'string') return item.trim();
        if (item && typeof item === 'object') {
          const { msg, loc } = item as { msg?: unknown; loc?: unknown };
          if (typeof msg === 'string' && msg) {
            const campo = nombreCampo(loc);
            return campo ? `${campo}: ${msg}` : msg;
          }
        }
        return '';
      })
      .filter(Boolean)
      .join('; ');
  }
  if (detail && typeof detail === 'object') {
    const o = detail as Record<string, unknown>;
    for (const clave of ['message', 'msg', 'mensaje']) {
      const v = o[clave];
      if (typeof v === 'string' && v.trim()) return v.trim();
    }
    if (o.detail !== undefined) return extraerMensajeDetail422(o.detail);
    if (typeof o.error === 'string') return o.error;
  }
  return '';
}

