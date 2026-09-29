/**
 * `tipoTarifa` config — match exacto del backend.
 *
 * Backend: `TipoTarifaCreate` acepta SOLO `tipo` (str, ≤64).
 */
import type { CatalogConfig } from '../lib/configTypes';

export const tipoTarifaConfig: CatalogConfig = {
  resource: 'tipo-tarifa',
  tabKey: 'tipo-tarifa',
  singularLabel: 'Modalidad de tarifa',
  pluralLabel: 'Modalidades de tarifa',
  fields: [{ name: 'tipo', label: 'Modalidad', required: true }],
  columns: [{ key: 'tipo', label: 'Modalidad' }],
  defaults: { tipo: '' },
  toCreatePayload: (form) => ({ tipo: String(form.tipo ?? '').trim() }),
};
