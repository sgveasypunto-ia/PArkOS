/**
 * `costosServicios` config — match exacto del backend.
 *
 * Backend: `CostosServiciosCreate` acepta `concepto` (req, ≤255 —
 * business key), `costo` (Decimal opt), `tipo_calculo` (≤32 opt).
 *
 * El business key es `concepto`, NO `nombre`.
 */
import type { CatalogConfig } from '../lib/configTypes';

export const costosServiciosConfig: CatalogConfig = {
  resource: 'costos-servicios',
  tabKey: 'costos-servicios',
  singularLabel: 'Costo de servicio',
  pluralLabel: 'Costos de servicios',
  fields: [
    { name: 'concepto', label: 'Concepto', required: true },
    { name: 'costo', label: 'Costo', type: 'number' },
    { name: 'tipo_calculo', label: 'Tipo de cálculo' },
  ],
  columns: [
    { key: 'concepto', label: 'Concepto' },
    { key: 'costo', label: 'Costo' },
    { key: 'tipo_calculo', label: 'Tipo cálculo' },
  ],
  defaults: {
    concepto: '',
    costo: 0,
    tipo_calculo: '',
  },
  toCreatePayload: (form) => {
    const out: Record<string, unknown> = {
      concepto: String(form.concepto ?? '').trim(),
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
    return out;
  },
};
