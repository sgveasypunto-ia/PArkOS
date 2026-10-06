/**
 * Mapeo de errores del backend (suscripciones / placas / renovación) a
 * mensajes en español (es-CO). Los códigos vienen de `ClientesApiError.code`
 * (o, como respaldo, del texto del mensaje de cualquier `Error`).
 */
import { ClientesApiError } from '../api/clientesApi';

type Translate = (key: string, fallback: string, opts?: Record<string, unknown>) => string;

function codeOf(e: unknown): string | null {
  return e instanceof ClientesApiError ? e.code : null;
}

function has(e: unknown, code: string): boolean {
  if (codeOf(e) === code) return true;
  const message = e instanceof Error ? e.message : '';
  return message.includes(code);
}

function detailString(e: unknown, key: string): string | null {
  if (!(e instanceof ClientesApiError)) return null;
  const v = e.detail[key];
  return typeof v === 'string' || typeof v === 'number' ? String(v) : null;
}

/** Errors shared by the "add plate / vehicle to subscription" and renewal endpoints. */
function mapCommonError(e: unknown, t: Translate): string | null {
  if (has(e, 'permission_denied')) {
    return t(
      'suscripcionErrores.permisoDenegado',
      'No tiene permiso para esta acción. Solo el perfil supervisor puede agregar o quitar placas.',
    );
  }
  if (has(e, 'missing_sucursal_context')) {
    return t(
      'suscripcionErrores.sinSucursal',
      'Seleccione una sucursal en el selector superior antes de continuar.',
    );
  }
  if (has(e, 'unauthorized_sucursal_context')) {
    return t(
      'suscripcionErrores.sucursalNoAutorizada',
      'No tiene acceso a la sucursal seleccionada.',
    );
  }
  if (has(e, 'subscripcion_no_encontrada')) {
    return t('suscripcionErrores.suscripcionNoEncontrada', 'La suscripción no existe o ya no está vigente.');
  }
  if (has(e, 'cantidad_vehiculos_excede_plan') || has(e, 'cantidad_maxima_excedida')) {
    return t(
      'suscripcionForm.errorCantidadExcede',
      'Se superó la cantidad máxima de vehículos permitida por el plan.',
    );
  }
  if (has(e, 'tipo_vehiculo_mixto_no_permitido') || has(e, 'tipo_vehiculo_incompatible')) {
    return t(
      'suscripcionForm.errorTipoMixto',
      'Este plan exige que todos los vehículos sean del mismo tipo.',
    );
  }
  return null;
}

/** Error when adding a vehicle/plate to a subscription. */
export function mapVehiculoError(e: unknown, t: Translate): string {
  // 409 `placa_con_suscripcion_activa` (current) / 422 `placa_con_suscripcion_vigente` (legacy alias).
  if (has(e, 'placa_con_suscripcion_activa') || has(e, 'placa_con_suscripcion_vigente')) {
    const placa = detailString(e, 'placa');
    return placa
      ? t(
          'suscripcionForm.errorPlacaActivaConPlaca',
          'La placa {{placa}} ya está en otra suscripción activa de esta sucursal.',
          { placa },
        )
      : t(
          'suscripcionForm.errorPlacaVigente',
          'Esa placa ya está en otra suscripción activa de esta sucursal.',
        );
  }
  if (has(e, 'vehiculo_ya_inscrito')) {
    return t('suscripcionForm.errorYaInscrito', 'Ese vehículo ya está inscrito en esta suscripción.');
  }
  if (has(e, 'vehiculo_no_encontrado')) {
    return t('suscripcionErrores.vehiculoNoEncontrado', 'El vehículo no existe o ya no está vigente.');
  }
  if (has(e, 'tipo_vehiculo_plan_incompatible')) {
    const tipoPlan = detailString(e, 'tipo_plan');
    return tipoPlan
      ? t(
          'suscripcionErrores.tipoPlanIncompatibleConTipo',
          'El tipo del vehículo no es compatible con el plan ({{tipoPlan}}).',
          { tipoPlan },
        )
      : t(
          'suscripcionErrores.tipoPlanIncompatible',
          'El tipo del vehículo no es compatible con el plan seleccionado.',
        );
  }
  return (
    mapCommonError(e, t) ??
    t('suscripcionForm.errorVehiculoGenerico', 'No se pudo agregar el vehículo.')
  );
}

/** Error when renewing a subscription (`POST .../renovar`). */
export function mapRenovacionError(e: unknown, t: Translate): string {
  if (has(e, 'idempotency_key_requerido')) {
    return t('renovacion.errorIdempotencia', 'No se pudo identificar el intento de renovación. Reintente.');
  }
  if (has(e, 'voucher_requerido')) {
    return t('renovacion.errorVoucher', 'El datáfono exige la referencia del voucher.');
  }
  if (has(e, 'renovacion_fuera_de_ventana')) {
    const dias = detailString(e, 'dias_restantes');
    const ventana = detailString(e, 'ventana_dias');
    return t(
      'renovacion.errorFueraDeVentana',
      'Todavía no se puede renovar: a la suscripción le quedan {{dias}} días y la renovación se habilita con {{ventana}} días o menos.',
      { dias: dias ?? '—', ventana: ventana ?? '10' },
    );
  }
  if (has(e, 'suscripcion_no_renovable')) {
    return t('renovacion.errorNoRenovable', 'Esta suscripción no se puede renovar.');
  }
  if (has(e, 'plan_no_vigente')) {
    return t('renovacion.errorPlanNoVigente', 'El plan de esta suscripción ya no está vigente.');
  }
  if (has(e, 'idempotency_key_conflict')) {
    return t(
      'renovacion.errorIdempotenciaConflicto',
      'Este intento ya fue procesado con otros datos. Cierre el diálogo y vuelva a intentarlo.',
    );
  }
  if (has(e, 'suscripcion_sin_vehiculos')) {
    return t('renovacion.errorSinVehiculos', 'La suscripción no tiene vehículos para renovar.');
  }
  if (has(e, 'vehiculo_no_resuelto')) {
    return t('renovacion.errorVehiculoNoResuelto', 'No se pudo resolver uno de los vehículos de la suscripción.');
  }
  if (has(e, 'placa_con_suscripcion_vigente') || has(e, 'placa_con_suscripcion_activa')) {
    const placa = detailString(e, 'placa');
    return t(
      'renovacion.errorPlacaVigente',
      'Una de las placas ya está en otra suscripción vigente{{placa}}.',
      { placa: placa ? ` (${placa})` : '' },
    );
  }
  if (has(e, 'plan_duracion_dias_invalido')) {
    return t('renovacion.errorDuracionInvalida', 'El plan no tiene una duración válida.');
  }
  if (has(e, 'iva_no_configurado')) {
    return t(
      'renovacion.errorIva',
      'No se pudo calcular el cobro: falta configurar el IVA. Contacte al administrador.',
    );
  }
  return (
    mapCommonError(e, t) ??
    t('renovacion.errorGenerico', 'No se pudo renovar la suscripción. Reintente.')
  );
}
