/**
 * `tipoSucursal` config — match exacto del backend.
 *
 * Backend: `TipoSucursalCreate` acepta `codigo` (req, ≤64), `nombre`
 * (≤255 opt), `descripcion` (opt), `caracteristicas` (JSONB dict opt).
 *
 * El form serializa `caracteristicas` como JSON string y lo parsea
 * antes de mandar (Pydantic espera dict, no string).
 */
import type { CatalogConfig } from '../lib/configTypes';

export const tipoSucursalConfig: CatalogConfig = {
  resource: 'tipo-sucursal',
  tabKey: 'tipo-sucursal',
  singularLabel: 'Tipo de sucursal',
  pluralLabel: 'Tipos de sucursal',
  fields: [
    { name: 'codigo', label: 'Código', required: true },
    { name: 'nombre', label: 'Nombre' },
    { name: 'descripcion', label: 'Descripción' },
    {
      name: 'caracteristicas',
      label: 'Características (JSON)',
    },
  ],
  columns: [
    { key: 'codigo', label: 'Código' },
    { key: 'nombre', label: 'Nombre' },
    { key: 'descripcion', label: 'Descripción' },
    {
      key: 'caracteristicas',
      label: 'Características',
      render: (value) => {
        if (value === null || value === undefined) return '—';
        if (typeof value === 'string') return value;
        try {
          return JSON.stringify(value);
        } catch {
          return '—';
        }
      },
    },
  ],
  defaults: {
    codigo: '',
    nombre: '',
    descripcion: '',
    caracteristicas: '{}',
  },
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
    const raw = form.caracteristicas;
    if (typeof raw === 'string' && raw.trim() !== '') {
      try {
        const parsed = JSON.parse(raw);
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
          out.caracteristicas = parsed;
        }
      } catch {
        // Mantener payload sin `caracteristicas` si el JSON es inválido;
        // el backend devolverá 422 con su propio mensaje.
      }
    }
    return out;
  },
};
