/**
 * `tipoSucursal` config — match exacto del backend.
 *
 * Backend: `TipoSucursalCreate` acepta `codigo` (req, ≤64), `nombre`
 * (≤255 opt), `descripcion` (opt), `caracteristicas` (JSONB dict opt).
 *
 * El form serializa `caracteristicas` como JSON string y lo parsea
 * antes de mandar (Pydantic espera dict, no string). La validación de
 * sintaxis corre en el cliente vía `validateForm` para que el usuario
 * vea el error inline (antes el form lo descartaba en silencio).
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
      label: 'Características',
      type: 'textarea',
      placeholder: '{"capacidad": 50, "techado": true}',
      hint: 'Diccionario JSON con propiedades libres. Opcional. Ej: {"capacidad": 50, "techado": true}',
      formatForEdit: (rowValue) => {
        if (rowValue === null || rowValue === undefined) return '{}';
        if (typeof rowValue === 'string') return rowValue;
        try {
          return JSON.stringify(rowValue, null, 2);
        } catch {
          return '{}';
        }
      },
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
  validateForm: (values) => {
    const raw = values.caracteristicas;
    if (typeof raw !== 'string' || raw.trim() === '') return null;
    try {
      const parsed = JSON.parse(raw);
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        return 'Características debe ser un objeto JSON (no array, no valor primitivo).';
      }
    } catch {
      return 'Características tiene JSON inválido. Revisá la sintaxis.';
    }
    return null;
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
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        out.caracteristicas = parsed;
      }
    }
    return out;
  },
};
