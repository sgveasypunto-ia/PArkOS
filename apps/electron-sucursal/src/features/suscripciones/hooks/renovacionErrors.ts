/**
 * `renovacionErrors.ts` — typed errors + es-CO messages for the renewal
 * endpoint's error contract (PT-3). Every code the backend can answer is
 * covered; unknown ones fall back to a generic message.
 */

export type RenovacionErrorCode =
  | 'idempotency_key_requerido'
  | 'voucher_requerido'
  | 'missing_sucursal_context'
  | 'permission_denied'
  | 'subscripcion_no_encontrada'
  | 'renovacion_fuera_de_ventana'
  | 'suscripcion_no_renovable'
  | 'plan_no_vigente'
  | 'idempotency_key_conflict'
  | 'placa_con_suscripcion_vigente'
  | 'suscripcion_sin_vehiculos'
  | 'vehiculo_no_resuelto'
  | 'cantidad_maxima_excedida'
  | 'tipo_vehiculo_incompatible'
  | 'plan_duracion_dias_invalido'
  | 'iva_no_configurado'
  | 'desconocido';

const KNOWN: ReadonlySet<string> = new Set<RenovacionErrorCode>([
  'idempotency_key_requerido',
  'voucher_requerido',
  'missing_sucursal_context',
  'permission_denied',
  'subscripcion_no_encontrada',
  'renovacion_fuera_de_ventana',
  'suscripcion_no_renovable',
  'plan_no_vigente',
  'idempotency_key_conflict',
  'placa_con_suscripcion_vigente',
  'suscripcion_sin_vehiculos',
  'vehiculo_no_resuelto',
  'cantidad_maxima_excedida',
  'tipo_vehiculo_incompatible',
  'plan_duracion_dias_invalido',
  'iva_no_configurado',
]);

export class RenovacionError extends Error {
  public readonly status: number;
  public readonly code: RenovacionErrorCode;
  public readonly dias_restantes: number | null;
  public readonly ventana_dias: number | null;
  public readonly placa: string | null;

  constructor(
    status: number,
    code: RenovacionErrorCode,
    extra: { dias_restantes?: number; ventana_dias?: number; placa?: string } = {},
  ) {
    super(code);
    this.name = 'RenovacionError';
    this.status = status;
    this.code = code;
    this.dias_restantes = extra.dias_restantes ?? null;
    this.ventana_dias = extra.ventana_dias ?? null;
    this.placa = extra.placa ?? null;
  }

  /**
   * True when the failure is definitive for THIS attempt (a new attempt
   * must use a fresh Idempotency-Key). Network/5xx-style failures keep the
   * key so a retry replays instead of double-charging.
   */
  get esDefinitivo(): boolean {
    return this.status >= 400 && this.status < 500;
  }
}

interface RenovacionBody {
  error?: string;
  dias_restantes?: number;
  ventana_dias?: number;
  placa?: string;
}

function parseBody(body: string): RenovacionBody | null {
  try {
    const parsed = JSON.parse(body) as { detail?: unknown } & RenovacionBody;
    const detail = parsed.detail;
    if (detail && typeof detail === 'object') return detail as RenovacionBody;
    return parsed;
  } catch {
    return null;
  }
}

/** Maps an HTTP failure to `RenovacionError` (always returns one). */
export function mapRenovacionHttpError(status: number, body: string): RenovacionError {
  const parsed = parseBody(body);
  const raw = parsed?.error ?? '';
  const code = (KNOWN.has(raw) ? raw : 'desconocido') as RenovacionErrorCode;
  return new RenovacionError(status, code, {
    dias_restantes: parsed?.dias_restantes,
    ventana_dias: parsed?.ventana_dias,
    placa: parsed?.placa,
  });
}

type Translate = (key: string, opts?: Record<string, unknown>) => string;

export function renovacionErrorMessage(err: unknown, t: Translate): string {
  if (!(err instanceof RenovacionError)) {
    return t('suscripciones:renovar.errors.desconocido', {
      defaultValue: 'No se pudo renovar la suscripción. Intentá de nuevo.',
    });
  }
  switch (err.code) {
    case 'renovacion_fuera_de_ventana':
      return t('suscripciones:renovar.errors.renovacion_fuera_de_ventana', {
        dias: err.dias_restantes ?? '',
        ventana: err.ventana_dias ?? 10,
        defaultValue: `Todavía no se puede renovar: faltan ${err.dias_restantes ?? 'más'} días y la renovación se habilita cuando queden ${err.ventana_dias ?? 10} o menos.`,
      });
    case 'idempotency_key_requerido':
      return t('suscripciones:renovar.errors.idempotency_key_requerido', {
        defaultValue: 'No se pudo identificar el intento de renovación. Intentá de nuevo.',
      });
    case 'voucher_requerido':
      return t('suscripciones:renovar.errors.voucher_requerido', {
        defaultValue: 'Ingresá el número de voucher del datáfono.',
      });
    case 'missing_sucursal_context':
      return t('suscripciones:renovar.errors.missing_sucursal_context', {
        defaultValue:
          'No se pudo identificar la sucursal de la sesión. Cerrá sesión e ingresá de nuevo.',
      });
    case 'permission_denied':
      return t('suscripciones:renovar.errors.permission_denied', {
        defaultValue: 'Tu usuario no tiene permiso para renovar suscripciones.',
      });
    case 'subscripcion_no_encontrada':
      return t('suscripciones:renovar.errors.subscripcion_no_encontrada', {
        defaultValue: 'La suscripción no existe o ya no está activa en esta sucursal.',
      });
    case 'suscripcion_no_renovable':
      return t('suscripciones:renovar.errors.suscripcion_no_renovable', {
        defaultValue: 'Esta suscripción no se puede renovar (ya fue renovada o está cancelada).',
      });
    case 'plan_no_vigente':
      return t('suscripciones:renovar.errors.plan_no_vigente', {
        defaultValue: 'El plan de esta suscripción ya no está vigente. Vendé una suscripción nueva.',
      });
    case 'idempotency_key_conflict':
      return t('suscripciones:renovar.errors.idempotency_key_conflict', {
        defaultValue:
          'Este intento de renovación ya se había enviado con otros datos. Cerrá esta pantalla y volvé a intentar.',
      });
    case 'placa_con_suscripcion_vigente':
      return t('suscripciones:renovar.errors.placa_con_suscripcion_vigente', {
        placa: err.placa ?? '',
        defaultValue: `La placa ${err.placa ?? ''} ya tiene otra suscripción vigente en esta sucursal.`,
      });
    case 'suscripcion_sin_vehiculos':
      return t('suscripciones:renovar.errors.suscripcion_sin_vehiculos', {
        defaultValue: 'La suscripción no tiene vehículos inscritos para renovar.',
      });
    case 'vehiculo_no_resuelto':
      return t('suscripciones:renovar.errors.vehiculo_no_resuelto', {
        defaultValue: 'No se pudo resolver uno de los vehículos de la suscripción.',
      });
    case 'cantidad_maxima_excedida':
      return t('suscripciones:renovar.errors.cantidad_maxima_excedida', {
        defaultValue: 'La cantidad de vehículos supera el máximo del plan.',
      });
    case 'tipo_vehiculo_incompatible':
      return t('suscripciones:renovar.errors.tipo_vehiculo_incompatible', {
        defaultValue: 'Los vehículos de la suscripción no coinciden con el tipo exigido por el plan.',
      });
    case 'plan_duracion_dias_invalido':
      return t('suscripciones:renovar.errors.plan_duracion_dias_invalido', {
        defaultValue: 'El plan tiene una duración inválida. Avisá al administrador.',
      });
    case 'iva_no_configurado':
      return t('suscripciones:renovar.errors.iva_no_configurado', {
        defaultValue: 'No hay IVA configurado en la sucursal. Avisá al administrador.',
      });
    default:
      return t('suscripciones:renovar.errors.desconocido', {
        defaultValue: 'No se pudo renovar la suscripción. Intentá de nuevo.',
      });
  }
}
