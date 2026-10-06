/**
 * `resumenCierre.ts` — single source of truth for the content of the
 * read-only post-close turn summary (PT-5).
 *
 * The same `sections` feed the on-screen `<ResumenCierreTurno>` and the
 * PDF export, so what the operator reads is exactly what they download.
 *
 * Sources (all available only AFTER the close was submitted — the blind
 * count is respected, nothing here is requested before the POST):
 *   - `POST /caja/arqueo` response: esperado / contado / diferencia (efectivo).
 *   - `PUT /caja-sesion/sesion/{uuid}/cerrar` response: base + hora de cierre.
 *   - `GET /operacion/mi-turno/resumen-cierre`: totales por medio de pago,
 *     nº de transacciones, ingresos/salidas, reversos. Optional: when that
 *     call fails the summary still renders with the rest.
 */
import type { TFunction } from 'i18next';

import type { ResumenCierreTurnoRead } from '../../../lib/api/schemas/resumen-cierre-turno';
import type { ResumenCierrePdfSection } from '../../../lib/print/resumenCierrePdf';
import type { SesionRead } from '../api/sesionActivaApi';
import type { ArqueoSubmitResult } from '../hooks/useArqueo';
import { formatCOP, formatFechaHoraCorta } from './format';

export interface ResumenCierreInput {
  sesion: SesionRead;
  arqueo: ArqueoSubmitResult;
  observaciones?: string;
  resumen: ResumenCierreTurnoRead | null;
}

const MEDIO_PAGO_LABELS: Record<string, string> = {
  efectivo: 'Efectivo',
  datafono: 'Datáfono',
  tarjeta: 'Tarjeta',
  transferencia: 'Transferencia',
  sin_especificar: 'Sin especificar',
};

export function labelMedioPago(medio: string): string {
  const known = MEDIO_PAGO_LABELS[medio];
  if (known !== undefined) return known;
  const spaced = medio.replace(/_/g, ' ');
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

function formatSigned(value: number): string {
  if (value === 0) return formatCOP(0);
  return `${value > 0 ? '+' : '-'}${formatCOP(Math.abs(value))}`;
}

export function buildResumenCierreSections(
  input: ResumenCierreInput,
  t: TFunction,
): ResumenCierrePdfSection[] {
  const { sesion, arqueo, observaciones, resumen } = input;
  const k = (key: string, defaultValue: string, opts?: Record<string, unknown>): string =>
    t(`caja:cerrarTurno.resumenCierre.${key}`, { defaultValue, ...opts });

  const contado = arqueo.valor_efectivo_reportado;
  const esperado = arqueo.valor_efectivo_esperado;
  const diferencia =
    arqueo.diferencia_efectivo ??
    (contado !== undefined && esperado !== undefined ? contado - esperado : undefined);
  const dash = '—';

  const sections: ResumenCierrePdfSection[] = [
    {
      heading: k('seccionTurno', 'Turno'),
      rows: [
        { label: k('apertura', 'Hora de apertura'), value: formatFechaHoraCorta(sesion.timestamp_apertura) },
        {
          label: k('cierre', 'Hora de cierre'),
          value: formatFechaHoraCorta(sesion.timestamp_cierre ?? new Date().toISOString()),
        },
      ],
    },
    {
      heading: k('seccionEfectivo', 'Cuadre de efectivo'),
      rows: [
        { label: k('base', 'Base (efectivo inicial)'), value: formatCOP(sesion.valor_inicial_efectivo) },
        {
          label: k('esperado', 'Efectivo esperado'),
          value: esperado !== undefined ? formatCOP(esperado) : dash,
        },
        {
          label: k('contado', 'Efectivo contado'),
          value: contado !== undefined ? formatCOP(contado) : dash,
        },
        {
          label: k('diferencia', 'Diferencia'),
          value: diferencia !== undefined ? formatSigned(diferencia) : dash,
        },
      ],
    },
  ];

  if (resumen === null) {
    sections.push({
      heading: k('seccionActividad', 'Actividad del turno'),
      rows: [
        {
          label: k('detalleNoDisponible', 'Detalle de pagos'),
          value: k('detalleNoDisponibleValor', 'No disponible'),
        },
      ],
    });
  } else {
    sections.push({
      heading: k('seccionActividad', 'Actividad del turno'),
      rows: [
        { label: k('ingresos', 'Ingresos'), value: String(resumen.ingresos_count) },
        { label: k('salidas', 'Salidas'), value: String(resumen.salidas_count) },
        {
          label: k('transacciones', 'Transacciones (pagos)'),
          value: String(resumen.transacciones_count),
        },
      ],
    });

    const pagoRows =
      resumen.medios_pago.length > 0
        ? resumen.medios_pago.map((m) => ({
            label: `${labelMedioPago(m.medio_pago)} (${m.pagos_count})`,
            value: formatCOP(m.total_cop),
          }))
        : [{ label: k('sinPagos', 'Sin pagos registrados'), value: formatCOP(0) }];
    if (resumen.reversos_count > 0) {
      pagoRows.push({
        label: k('reversos', 'Reversos ({{n}})', { n: resumen.reversos_count }),
        value: formatCOP(resumen.reversos_total_cop),
      });
    }
    sections.push({ heading: k('seccionMedios', 'Totales por medio de pago'), rows: pagoRows });
  }

  if (observaciones !== undefined && observaciones !== '') {
    sections.push({
      heading: k('seccionObservaciones', 'Observaciones'),
      rows: [{ label: k('observaciones', 'Observaciones del cierre'), value: observaciones }],
    });
  }

  return sections;
}
