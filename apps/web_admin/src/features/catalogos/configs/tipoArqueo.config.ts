/**
 * `tipoArqueo` config — match exacto del backend.
 *
 * Backend: `TipoArqueoCreate` acepta `codigo` (req, ≤64), `nombre`
 * (≤255 opt), `descripcion` (opt). El business key es `codigo`, no
 * `tipo`.
 */
import type { CatalogConfig } from '../lib/configTypes';

export const tipoArqueoConfig: CatalogConfig = {
  resource: 'tipo-arqueo',
  tabKey: 'tipo-arqueo',
  singularLabel: 'Tipo de arqueo',
  pluralLabel: 'Tipos de arqueo',
  fields: [
    { name: 'codigo', label: 'Código', required: true },
    { name: 'nombre', label: 'Nombre' },
    { name: 'descripcion', label: 'Descripción' },
  ],
  columns: [
    { key: 'codigo', label: 'Código' },
    { key: 'nombre', label: 'Nombre' },
    { key: 'descripcion', label: 'Descripción' },
  ],
  defaults: { codigo: '', nombre: '', descripcion: '' },
  toCreatePayload: (form) => {
    const out: Record<string, unknown> = {
      codigo: String(form.codigo ?? '').trim(),
    };
    if (form.nombre !== '' && form.nombre !== undefined && form.nombre !== null) {
      out.nombre = String(form.nombre).trim();
    }
    if (
      form.descripcion !== '' &&
      form.descripcion !== undefined &&
      form.descripcion !== null
    ) {
      out.descripcion = String(form.descripcion).trim();
    }
    return out;
  },
};
