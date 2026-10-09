/**
 * `tipoSubscripciones` config — match exacto del backend.
 *
 * Backend: `TipoSubscripcionesCreate` acepta `tipo` (req, ≤64),
 * `valor` (Decimal opt), `duracion_dias` (int opt),
 * `cantidad_maxima_vehiculos` (int opt), `mismo_tipo_vehiculo` (bool opt),
 * `tipo_cliente_permitido` (str ≤64 opt), `uuid_tipo_vehiculo` (uuid opt;
 * NULL = plan válido para cualquier tipo de vehículo, PT-2).
 *
 * Ambos selects (`uuid_tipo_vehiculo`, `tipo_cliente_permitido`) se
 * rinden SIN opción vacía: el router genérico usa `exclude_none`, así
 * que un plan con tipo asignado no puede volver a NULL — había que
 * crear un plan nuevo. Mostrar "Cualquiera" como opción era confuso
 * porque la rama de "volver a Cualquiera" siempre reventaba tarde
 * (vía `validateUpdate` o 422 del backend). Se sacó.
 */
import { createElement } from 'react';

import { TipoVehiculoCell } from '../components/TipoVehiculoCell';
import type { CatalogConfig } from '../lib/configTypes';

export const tipoSubscripcionesConfig: CatalogConfig = {
  resource: 'tipo-subscripciones',
  tabKey: 'tipo-subscripciones',
  singularLabel: 'Tipo de subscripción',
  pluralLabel: 'Tipos de subscripción',
  fields: [
    { name: 'tipo', label: 'Tipo', required: true },
    { name: 'valor', label: 'Valor', type: 'number' },
    { name: 'duracion_dias', label: 'Duración (días)', type: 'number' },
    {
      name: 'cantidad_maxima_vehiculos',
      label: 'Cantidad máxima de vehículos',
      type: 'number',
    },
    {
      name: 'mismo_tipo_vehiculo',
      label: 'Mismo tipo de vehículo',
      type: 'checkbox',
    },
    {
      name: 'tipo_cliente_permitido',
      label: 'Tipo de cliente permitido',
      type: 'select',
      optionsResource: 'tipo-persona',
      optionsLabelKey: 'tipo',
      optionsValueKey: 'tipo',
      allowEmpty: false,
      hint: 'Filtrá los planes por tipo de persona.',
    },
    {
      name: 'uuid_tipo_vehiculo',
      label: 'Tipo de vehículo',
      type: 'select',
      required: true,
      optionsResource: 'tipos-vehiculo',
      optionsLabelKey: 'tipo',
      allowEmpty: false,
      hint: 'Elegí el tipo de vehículo al que aplica este plan.',
    },
  ],
  columns: [
    { key: 'tipo', label: 'Tipo' },
    { key: 'valor', label: 'Valor' },
    { key: 'duracion_dias', label: 'Duración (días)' },
    {
      key: 'cantidad_maxima_vehiculos',
      label: 'Cantidad máx. vehículos',
    },
    { key: 'mismo_tipo_vehiculo', label: 'Mismo tipo' },
    { key: 'tipo_cliente_permitido', label: 'Tipo cliente' },
    {
      key: 'uuid_tipo_vehiculo',
      label: 'Tipo de vehículo',
      render: (value) =>
        createElement(TipoVehiculoCell, {
          uuid: typeof value === 'string' && value !== '' ? value : null,
        }),
    },
  ],
  defaults: {
    tipo: '',
    valor: 0,
    duracion_dias: 30,
    cantidad_maxima_vehiculos: 1,
    mismo_tipo_vehiculo: false,
    tipo_cliente_permitido: '',
    uuid_tipo_vehiculo: '',
  },
  toCreatePayload: (form) => ({
    tipo: String(form.tipo ?? '').trim(),
    ...(form.valor !== '' && form.valor !== undefined && form.valor !== null
      ? { valor: Number(form.valor) }
      : {}),
    ...(form.duracion_dias !== '' &&
    form.duracion_dias !== undefined &&
    form.duracion_dias !== null
      ? { duracion_dias: Number(form.duracion_dias) }
      : {}),
    ...(form.cantidad_maxima_vehiculos !== '' &&
    form.cantidad_maxima_vehiculos !== undefined &&
    form.cantidad_maxima_vehiculos !== null
      ? { cantidad_maxima_vehiculos: Number(form.cantidad_maxima_vehiculos) }
      : {}),
    ...(form.mismo_tipo_vehiculo === true
      ? { mismo_tipo_vehiculo: true }
      : {}),
    ...(form.tipo_cliente_permitido !== '' &&
    form.tipo_cliente_permitido !== undefined &&
    form.tipo_cliente_permitido !== null
      ? { tipo_cliente_permitido: String(form.tipo_cliente_permitido).trim() }
      : {}),
    ...(typeof form.uuid_tipo_vehiculo === 'string' && form.uuid_tipo_vehiculo !== ''
      ? { uuid_tipo_vehiculo: form.uuid_tipo_vehiculo }
      : {}),
  }),
};
