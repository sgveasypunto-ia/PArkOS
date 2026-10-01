/**
 * `tiposVehiculo` config — match exacto del backend.
 *
 * Backend: `TiposVehiculoCreate` acepta SOLO `tipo` (str, ≤64).
 */
import type { CatalogConfig } from '../lib/configTypes';

export const tiposVehiculoConfig: CatalogConfig = {
  resource: 'tipos-vehiculo',
  tabKey: 'tipos-vehiculo',
  singularLabel: 'Tipo de vehículo',
  pluralLabel: 'Tipos de vehículo',
  fields: [{ name: 'tipo', label: 'Tipo', required: true }],
  columns: [{ key: 'tipo', label: 'Tipo' }],
  defaults: { tipo: '' },
  toCreatePayload: (form) => ({ tipo: String(form.tipo ?? '').trim() }),
};
