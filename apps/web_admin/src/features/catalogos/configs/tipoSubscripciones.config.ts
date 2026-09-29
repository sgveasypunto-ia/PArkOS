import type { CatalogConfig } from '../lib/configTypes';

export const tipoSubscripcionesConfig: CatalogConfig = {
  resource: 'tipo-subscripciones',
  tabKey: 'tipo-subscripciones',
  singularLabel: 'Tipo de subscripción',
  pluralLabel: 'Tipos de subscripción',
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
