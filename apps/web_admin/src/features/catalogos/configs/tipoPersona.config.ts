/**
 * `tipoPersona` config — match exacto del backend.
 *
 * Backend: `TipoPersonaCreate` acepta SOLO `tipo` (str, ≤64). El backend
 * rechaza cualquier otro campo (`extra="forbid"`).
 */
import type { CatalogConfig } from '../lib/configTypes';

export const tipoPersonaConfig: CatalogConfig = {
  resource: 'tipo-persona',
  tabKey: 'tipo-persona',
  singularLabel: 'Tipo de persona',
  pluralLabel: 'Tipos de persona',
  fields: [{ name: 'tipo', label: 'Tipo', required: true }],
  columns: [{ key: 'tipo', label: 'Tipo' }],
  defaults: { tipo: '' },
  toCreatePayload: (form) => ({ tipo: String(form.tipo ?? '').trim() }),
};
