import type { CatalogConfig } from '../lib/configTypes';

export const impuestosConfig: CatalogConfig = {
  resource: 'impuestos',
  tabKey: 'impuestos',
  singularLabel: 'Impuesto',
  pluralLabel: 'Impuestos',
  fields: [
    { name: 'nombre', label: 'Nombre', required: true },
    { name: 'porcentaje', label: 'Porcentaje (0-100)', type: 'number', required: true },
    { name: 'descripcion', label: 'Descripción', required: false },
  ],
  columns: [
    { key: 'nombre', label: 'Nombre' },
    {
      key: 'porcentaje',
      label: 'Porcentaje',
      render: (v) => `${v ?? 0}%`,
    },
    { key: 'descripcion', label: 'Descripción' },
  ],
  defaults: { nombre: '', porcentaje: 19, descripcion: '' },
  toCreatePayload: (form) => ({ ...form }),
};
