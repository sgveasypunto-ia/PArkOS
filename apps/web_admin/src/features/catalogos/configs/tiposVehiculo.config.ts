import type { CatalogConfig } from '../lib/configTypes';

export const tiposVehiculoConfig: CatalogConfig = {
  resource: 'tipos-vehiculo',
  tabKey: 'tipos-vehiculo',
  singularLabel: 'Tipo de vehículo',
  pluralLabel: 'Tipos de vehículo',
  fields: [
    { name: 'tipo', label: 'Tipo', required: true },
    { name: 'descripcion', label: 'Descripción', required: false },
  ],
  columns: [
    { key: 'tipo', label: 'Tipo' },
    { key: 'descripcion', label: 'Descripción' },
  ],
  defaults: { tipo: '', descripcion: '' },
  toCreatePayload: (form) => ({ ...form }),
};
