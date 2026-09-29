import type { CatalogConfig } from '../lib/configTypes';

export const tipoSucursalConfig: CatalogConfig = {
  resource: 'tipo-sucursal',
  tabKey: 'tipo-sucursal',
  singularLabel: 'Tipo de sucursal',
  pluralLabel: 'Tipos de sucursal',
  fields: [
    { name: 'tipo', label: 'Tipo', required: true },
    { name: 'caracteristicas', label: 'Características (JSON)', required: false },
  ],
  columns: [
    { key: 'tipo', label: 'Tipo' },
    { key: 'caracteristicas', label: 'Características' },
  ],
  defaults: { tipo: '', caracteristicas: '{}' },
  toCreatePayload: (form) => ({
    ...form,
    caracteristicas:
      typeof form.caracteristicas === 'string' && form.caracteristicas.trim() !== ''
        ? JSON.parse(form.caracteristicas as string)
        : {},
  }),
};
