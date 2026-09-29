import type { CatalogConfig } from '../lib/configTypes';

export const tipoPersonaConfig: CatalogConfig = {
  resource: 'tipo-persona',
  tabKey: 'tipo-persona',
  singularLabel: 'Tipo de persona',
  pluralLabel: 'Tipos de persona',
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
