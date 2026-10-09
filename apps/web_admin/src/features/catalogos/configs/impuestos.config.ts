/**
 * `impuestos` config — match exacto del backend.
 *
 * Backend: `ImpuestosCreate` acepta `nombre` (opt, ≤255), `codigo`
 * (req, ≤64 — business key), `porcentaje` (Decimal opt), `tipo_calculo`
 * (≤32 opt), `base_calculo` (≤32 opt).
 *
 * NOTA: el business key es `codigo`, NO `nombre` ni `tipo`.
 * `tipo_calculo` y `base_calculo` son strings libres en el backend,
 * pero la UI los restringe a los valores que el sistema efectivamente
 * usa (visto en `test_calcular_cotizacion_db.py` + repos de impuestos
 * y de cotización): "porcentaje"/"fijo" y "subtotal"/"total".
 */
import type { CatalogConfig } from '../lib/configTypes';

export const impuestosConfig: CatalogConfig = {
  resource: 'impuestos',
  tabKey: 'impuestos',
  singularLabel: 'Impuesto',
  pluralLabel: 'Impuestos',
  fields: [
    { name: 'codigo', label: 'Código', required: true },
    { name: 'nombre', label: 'Nombre' },
    { name: 'porcentaje', label: 'Porcentaje (0-100)', type: 'number' },
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
    { key: 'codigo', label: 'Código' },
    { key: 'nombre', label: 'Nombre' },
    {
      key: 'porcentaje',
      label: 'Porcentaje',
      render: (value) => {
        if (value === null || value === undefined) return '—';
        const n = typeof value === 'number' ? value : Number(value);
        return Number.isFinite(n) ? `${n.toFixed(2)}%` : '—';
      },
    },
    { key: 'tipo_calculo', label: 'Tipo cálculo' },
    { key: 'base_calculo', label: 'Base cálculo' },
  ],
  defaults: {
    codigo: '',
    nombre: '',
    porcentaje: 19,
    tipo_calculo: '',
    base_calculo: '',
  },
  toCreatePayload: (form) => {
    const out: Record<string, unknown> = {
      codigo: String(form.codigo ?? '').trim(),
    };
    if (form.nombre !== '' && form.nombre !== undefined && form.nombre !== null) {
      out.nombre = String(form.nombre).trim();
    }
    if (
      form.porcentaje !== '' &&
      form.porcentaje !== undefined &&
      form.porcentaje !== null
    ) {
      out.porcentaje = Number(form.porcentaje);
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
