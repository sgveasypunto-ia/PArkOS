import type { CatalogConfig } from '../lib/configTypes';

export const otrosCobrosConfig: CatalogConfig = {
  resource: 'otros-cobros',
  tabKey: 'otros-cobros',
  singularLabel: 'Otro cobro',
  pluralLabel: 'Otros cobros',
  fields: [
    { name: 'nombre', label: 'Nombre', required: true },
    { name: 'descripcion', label: 'Descripción', required: false },
  ],
  columns: [
    { key: 'nombre', label: 'Nombre' },
    { key: 'descripcion', label: 'Descripción' },
  ],
  defaults: { nombre: '', descripcion: '' },
  toCreatePayload: (form) => ({ ...form }),
};
