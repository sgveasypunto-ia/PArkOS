/**
 * `<FacturaImpuestosDetalle />` — shared money section of every invoice
 * display: subtotal (taxable base), discount, ONE row per applied tax
 * (name, rate, taxable base, amount — the persisted `factura_impuestos`
 * snapshot) and the total.
 *
 * Used by `<FacturaDisplayModal />` for every invoice type (rotación,
 * salida, servicio suelto, venta/renovación de suscripción) so they all show
 * the same breakdown. Amounts carry cents (fiscal document: base + tax must
 * reconcile with the total to the cent, whole-peso rounding could drift 1 COP).
 */
import { useTranslation } from 'react-i18next';

import type { FacturaRead } from '../api/facturaApi';

const copDecimal = new Intl.NumberFormat('es-CO', {
  style: 'currency',
  currency: 'COP',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

function money(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return copDecimal.format(value);
}

/** Dashed separator between ticket line-groups (same grammar as the modal). */
function TicketDivider(): JSX.Element {
  return <div className="mt-1 border-t border-dashed border-neutral-400 pt-1" />;
}

export interface FacturaImpuestosDetalleProps {
  factura: Pick<FacturaRead, 'subtotal' | 'descuento' | 'impuestos' | 'total'>;
}

export function FacturaImpuestosDetalle({ factura: f }: FacturaImpuestosDetalleProps): JSX.Element {
  const { t } = useTranslation(['facturacion']);
  return (
    <div data-testid="factura-display-totales">
      <TicketDivider />
      <div className="flex justify-between gap-2">
        <span className="min-w-0 truncate">
          {t('facturacion:display.subtotalBase', { defaultValue: 'Subtotal (base)' })}
        </span>
        <span data-testid="factura-display-subtotal" className="shrink-0 tabular-nums">
          {money(f.subtotal)}
        </span>
      </div>
      {(f.descuento ?? 0) > 0 && (
        <div className="flex justify-between gap-2">
          <span className="min-w-0 truncate">
            {t('facturacion:display.descuento', { defaultValue: 'Descuento' })}
          </span>
          <span className="shrink-0 tabular-nums">− {money(f.descuento)}</span>
        </div>
      )}
      {f.impuestos.map((imp) => (
        <div key={imp.uuid} data-testid="factura-display-impuesto-grupo">
          <div className="flex justify-between gap-2" data-testid="factura-display-impuesto">
            <span className="min-w-0 truncate">
              {imp.nombre_impuesto ?? imp.codigo_impuesto ?? 'Impuesto'}{' '}
              {imp.porcentaje_aplicado !== null &&
                imp.porcentaje_aplicado !== undefined &&
                `(${(imp.porcentaje_aplicado * 100).toFixed(2)}%)`}
            </span>
            <span className="shrink-0 tabular-nums">{money(imp.valor)}</span>
          </div>
          <div
            className="flex justify-between gap-2 pl-2 text-neutral-600"
            data-testid="factura-display-impuesto-base"
          >
            <span className="min-w-0 truncate">
              {t('facturacion:display.baseImpuesto', { defaultValue: 'Base' })}
            </span>
            <span className="shrink-0 tabular-nums">{money(imp.base_calculo)}</span>
          </div>
        </div>
      ))}
      <div className="mt-1 flex justify-between gap-2 border-t border-dashed border-neutral-400 pt-1 font-bold">
        <span className="min-w-0 truncate">
          {t('facturacion:display.total', { defaultValue: 'TOTAL' })}
        </span>
        <span data-testid="factura-display-total" className="shrink-0 tabular-nums">
          {money(f.total)}
        </span>
      </div>
    </div>
  );
}
