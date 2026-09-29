import type { CatalogConfig } from '../lib/configTypes';

export const tipoTarifaConfig: CatalogConfig = {
  resource: 'tipo-tarifa',
  tabKey: 'tipo-tarifa',
  singularLabel: 'Modalidad de tarifa',
  pluralLabel: 'Modalidades de tarifa',
  fields: [
    { name: 'tipo', label: 'Modalidad', required: true },
    { name: 'descripcion', label: 'Descripción', required: false },
  ],
  columns: [
    { key: 'tipo', label: 'Modalidad' },
    { key: 'descripcion', label: 'Descripción' },
  ],
  defaults: { tipo: '', descripcion: '' },
  toCreatePayload: (form) => ({ ...form }),
};
