/**
 * `cuposErrorMessage` — maps the typed errors of the add/remove plate hooks
 * (PT-2) to a clear es-CO message. Pure: receives the `t` function so it can
 * be unit-tested without i18n bootstrapping.
 */
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import {
  CuposCantidadMaximaError,
  CuposContextoSucursalError,
  CuposPermisoDenegadoError,
  CuposPlacaConSuscripcionActivaError,
  CuposSubscripcionNoEncontradaError,
  CuposTipoIncompatibleError,
  CuposTipoPlanIncompatibleError,
  CuposVehiculoInscritoNoEncontradoError,
  CuposVehiculoYaInscritoError,
} from '../hooks/cuposErrors';

type Translate = (key: string, opts?: Record<string, unknown>) => string;

export function cuposErrorMessage(err: unknown, t: Translate): string {
  if (err instanceof CuposPermisoDenegadoError) {
    return t('suscripciones:cupos.errors.permission_denied', {
      defaultValue: 'Solo el supervisor puede agregar o quitar placas de una suscripción.',
    });
  }
  if (err instanceof CuposContextoSucursalError) {
    return err.status === 400
      ? t('suscripciones:cupos.errors.missing_sucursal_context', {
          defaultValue:
            'No se pudo identificar la sucursal de la sesión. Cerrá sesión e ingresá de nuevo.',
        })
      : t('suscripciones:cupos.errors.unauthorized_sucursal_context', {
          defaultValue: 'Tu usuario no tiene acceso a esta sucursal.',
        });
  }
  if (err instanceof CuposSubscripcionNoEncontradaError) {
    return t('suscripciones:cupos.errors.subscripcion_no_encontrada', {
      defaultValue: 'La suscripción ya no está activa en esta sucursal.',
    });
  }
  if (err instanceof CuposVehiculoInscritoNoEncontradoError) {
    return t('suscripciones:cupos.errors.vehiculo_inscrito_no_encontrado', {
      defaultValue: 'El vehículo ya no está inscrito en esta suscripción.',
    });
  }
  if (err instanceof CuposVehiculoYaInscritoError) {
    return t('suscripciones:cupos.errors.vehiculo_ya_inscrito', {
      placa: err.placa,
      defaultValue: `La placa ${err.placa} ya está inscrita en esta suscripción.`,
    });
  }
  if (err instanceof CuposPlacaConSuscripcionActivaError) {
    return t('suscripciones:cupos.errors.placa_con_suscripcion_activa', {
      placa: err.placa,
      defaultValue: `La placa ${err.placa} ya está en otra suscripción activa de esta sucursal.`,
    });
  }
  if (err instanceof CuposTipoPlanIncompatibleError) {
    const tipos = err.tipos_encontrados.join(', ');
    return t('suscripciones:cupos.errors.tipo_vehiculo_plan_incompatible', {
      tipoPlan: err.tipo_plan ?? '',
      tipos,
      defaultValue: err.tipo_plan
        ? `El plan es para vehículos tipo ${err.tipo_plan}; la placa corresponde a ${tipos || 'otro tipo'}.`
        : 'El tipo de vehículo de la placa no coincide con el plan.',
    });
  }
  if (err instanceof CuposTipoIncompatibleError) {
    return t('suscripciones:cupos.errors.tipo_vehiculo_incompatible', {
      defaultValue: 'Este plan exige que todos los vehículos sean del mismo tipo.',
    });
  }
  if (err instanceof CuposCantidadMaximaError) {
    return t('suscripciones:cupos.errors.cantidad_maxima_excedida', {
      max: err.max,
      defaultValue: 'El plan alcanzó su cantidad máxima de vehículos.',
    });
  }
  if (err instanceof ParkosHttpError && err.status === 401) {
    return t('suscripciones:cupos.errors.sesion_expirada', {
      defaultValue: 'Tu sesión expiró. Ingresá de nuevo.',
    });
  }
  return t('suscripciones:cupos.errors.generico', {
    defaultValue: 'No se pudo completar la operación. Intentá de nuevo.',
  });
}
