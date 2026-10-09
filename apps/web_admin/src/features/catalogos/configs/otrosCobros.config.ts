/**
 * `otrosCobros` config — match exacto del backend.
 *
 * Backend: `OtrosCobrosCreate` acepta `nombre` (req, ≤255 — business
 * key), `costo` (Decimal opt), `tipo_calculo` (≤32 opt),
 * `base_calculo` (≤32 opt).
 */
import type { CatalogConfig } from '../lib/configTypes';

export const otrosCobrosConfig: CatalogConfig = {
  resource: 'otros-cobros',
  tabKey: 'otros-cobros',
  singularLabel: 'Otro cobro',
  pluralLabel: 'Otros cobros',
  fields: [
    { name: 'nombre', label: 'Nombre', required: true },
    { name: 'costo', label: 'Costo', type: 'number' },
    {
      name: 'tipo_calculo',
      label: 'Tipo de cálculo',
      type: 'select',
      emptyOptionLabel: 'Sin definir',
      options: [
        { value: 'porcentaje', label: 'Porcentaje' },
        { value: 'fijo', label: 'Fijo' },
      ],
    },
    {
      name: 'base_calculo',
      label: 'Base de cálculo',
      type: 'select',
      emptyOptionLabel: 'Sin definir',
      options: [
        { value: 'subtotal', label: 'Subtotal' },
        { value: 'total', label: 'Total' },
      ],
    },
  ],
  columns: [
    { key: 'nombre', label: 'Nombre' },
    { key: 'costo', label: 'Costo' },
    { key: 'tipo_calculo', label: 'Tipo cálculo' },
    { key: 'base_calculo', label: 'Base cálculo' },
  ],
  defaults: {
    nombre: '',
    costo: 0,
    tipo_calculo: '',
    base_calculo: '',
  },
  toCreatePayload: (form) => {
    const out: Record<string, unknown> = {
      nombre: String(form.nombre ?? '').trim(),
    };
    if (form.costo !== '' && form.costo !== undefined && form.costo !== null) {
      out.costo = Number(form.costo);
    }
    if (
      form.tipo_calculo !== '' &&
      form.tipo_calculo !== undefined &&
      form.tipo_calculo !== null
    ) {
      out.tipo_calculo = String(form.tipo_calculo).trim();
    }
    if (
      form.base_calculo !== '' &&
      form.base_calculo !== undefined &&
      form.base_calculo !== null
    ) {
      out.base_calculo = String(form.base_calculo).trim();
    }
    return out;
  },
};
