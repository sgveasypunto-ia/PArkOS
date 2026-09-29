import type { CatalogConfig } from '../lib/configTypes';

export const costosServiciosConfig: CatalogConfig = {
  resource: 'costos-servicios',
  tabKey: 'costos-servicios',
  singularLabel: 'Costo de servicio',
  pluralLabel: 'Costos de servicios',
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
