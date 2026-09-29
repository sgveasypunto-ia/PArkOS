import type { CatalogConfig } from '../lib/configTypes';

export const tipoArqueoConfig: CatalogConfig = {
  resource: 'tipo-arqueo',
  tabKey: 'tipo-arqueo',
  singularLabel: 'Tipo de arqueo',
  pluralLabel: 'Tipos de arqueo',
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
