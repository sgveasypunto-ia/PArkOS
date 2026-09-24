/**
 * `<FacturaDisplayModal />` — HU-F8.4 post-pago breakdown display.
 *
 * After a successful `POST /api/v1/facturacion/factura`, the BE returns
 * the enriched `FacturaRead` (22 fields) with the operator-facing
 * breakdown:
 *   - Datos sucursal (razón social, NIT, dirección, régimen)
 *   - Datos cliente (consumidor final when NULL)
 *   - Datos vehículo (placa + minutos parked)
 *   - Items (líneas de factura)
 *   - Impuestos aplicados (snapshot porcentaje + valor)
 *   - Segregación de valores (subtotal + descuento + impuestos + total)
 *   - Medio de pago + vuelto/voucher
 *   - FE estado DIAN (when assigned)
 *   - Número de recibo (local receipt number per plan.md:473)
 *
 * The modal mounts OVER the PagoSheet (z-indexed higher than shadcn
 * `<Sheet>`) so the operator can review the breakdown before
 * dismissing the sheet. The thermal CU-15S print fires in parallel
 * (see PagoSheet.handleSubmit deferredSafePrint).
 *
 * `aria-modal="true"` + `<h1>` + WCAG 2.1 AA: this is the operator's
 * last visual confirmation that the cobro persisted; the modal must
 * be readable by keyboard + screen reader. shadcn `<Dialog>` provides
 * focus trap + Esc-to-close out of the box.
 */
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

import type { FacturaRead } from '../api/facturaApi';
import { formatCOP } from '../../caja/lib/format';

export interface FacturaDisplayModalProps {
  /** Enriched FacturaRead from the post-pago POST. NULL = modal hidden. */
  factura: FacturaRead | null;
  /** Operator dismisses the modal — PagoSheet clears state + closes sheet. */
  onClose: () => void;
}

/**
 * Format a backend number (Decimal serialized as JSON number — already
 * in COP units, NOT cents) to the canonical es-CO currency string via
 * `Intl.NumberFormat` (DEC-SUC-07). Suffix-free: the modal labels carry
 * the unit suffix to keep the formatter reusable for vueltos etc.
 */
function money(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return formatCOP(value);
}

function tiempoMinutos(minutos: number | null | undefined): string {
  if (minutos === null || minutos === undefined) return '—';
  const h = Math.floor(minutos / 60);
  const m = minutos % 60;
  if (h <= 0) return `${m} min`;
  return `${h} h ${m} min`;
}

export function FacturaDisplayModal({
  factura,
  onClose,
}: FacturaDisplayModalProps): JSX.Element {
  const { t } = useTranslation(['facturacion', 'common']);

  // shadcn Dialog accepts `open` as the canonical mount gate; we keep
  // the component always mounted but transparent when `factura` is
  // null so the operator's last-viewed data doesn't flicker on
  // re-render. The `<p>` with React refs would be over-engineering
  // here; a conditional Dialog open is the canonical pattern.
  const open = factura !== null;
  const f = factura;

  // Defensive: shadcn Dialog requires at least one child. When
  // `factura` is null we render an empty Dialog so the close
  // animation still plays before unmount.
  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) onClose(); }}>
      <DialogContent
        className="max-w-2xl max-h-[90vh] overflow-y-auto"
        data-testid="factura-display-modal"
        aria-describedby="factura-display-desc"
      >
        {f && (
          <>
            <DialogHeader>
              <DialogTitle data-testid="factura-display-titulo">
                {t('facturacion:display.titulo', { defaultValue: 'Factura emitida' })}
              </DialogTitle>
              <DialogDescription id="factura-display-desc">
                {t('facturacion:display.descripcion', {
                  defaultValue: `Recibo ${f.numero_recibo} — ${new Date(f.created_at).toLocaleString('es-CO')}`,
                })}
              </DialogDescription>
            </DialogHeader>

            {/* === Sección: Datos de la sucursal === */}
            <section className="space-y-1" data-testid="factura-display-sucursal">
              <h2 className="text-sm font-semibold text-muted-foreground">
                {t('facturacion:display.sucursal', { defaultValue: 'Emisor' })}
              </h2>
              <p className="text-base font-medium">
                {f.datos_sucursal.razon_social ?? '—'}
              </p>
              <p className="text-sm">
                NIT {f.datos_sucursal.nit ?? '—'}
                {f.datos_sucursal.regimen ? ` · ${f.datos_sucursal.regimen}` : ''}
              </p>
              {f.datos_sucursal.direccion && (
                <p className="text-sm">{f.datos_sucursal.direccion}</p>
              )}
              {f.datos_sucursal.telefono && (
                <p className="text-sm">{f.datos_sucursal.telefono}</p>
              )}
            </section>

            <hr className="border-border" />

            {/* === Sección: Cliente === */}
            <section className="space-y-1" data-testid="factura-display-cliente">
              <h2 className="text-sm font-semibold text-muted-foreground">
                {t('facturacion:display.cliente', { defaultValue: 'Cliente' })}
              </h2>
              {f.cliente ? (
                <>
                  <p className="text-base font-medium">
                    {f.cliente.nombre ?? '—'}{' '}
                    {f.cliente.apellido ? ` ${f.cliente.apellido}` : ''}
                  </p>
                  <p className="text-sm">
                    {f.cliente.nit ?? '—'}
                    {f.cliente.dv ? `-${f.cliente.dv}` : ''}
                  </p>
                  {f.cliente.email && (
                    <p className="text-sm text-muted-foreground">{f.cliente.email}</p>
                  )}
                </>
              ) : (
                <p className="text-base font-medium">
                  {t('facturacion:display.consumidorFinal', { defaultValue: 'Consumidor final' })}
                </p>
              )}
            </section>

            {/* === Sección: Vehículo + minutos === */}
            {f.datos_vehiculo && (
              <>
                  <hr className="border-border" />
                  <section className="space-y-1" data-testid="factura-display-vehiculo">
                    <h2 className="text-sm font-semibold text-muted-foreground">
                      {t('facturacion:display.vehiculo', { defaultValue: 'Vehículo' })}
                    </h2>
                    <p className="text-2xl font-bold tracking-wider font-mono">
                      {f.datos_vehiculo.placa ?? '—'}
                    </p>
                    <p className="text-sm" data-testid="factura-display-minutos">
                      {t('facturacion:display.tiempo', { defaultValue: 'Tiempo' })}:{' '}
                      <span className="font-medium">
                        {tiempoMinutos(f.datos_vehiculo.minutos)}
                      </span>
                    </p>
                  </section>
                </>
            )}

            <hr className="border-border" />

            {/* === Sección: Líneas / items === */}
            <section className="space-y-2" data-testid="factura-display-items">
              <h2 className="text-sm font-semibold text-muted-foreground">
                {t('facturacion:display.items', { defaultValue: 'Detalle' })}
              </h2>
              {f.items.length === 0 ? (
                <p className="text-sm text-muted-foreground">—</p>
              ) : (
                <ul className="divide-y divide-border text-sm">
                  {f.items.map((item) => (
                    <li
                      key={item.uuid}
                      className="flex justify-between gap-2 py-1"
                      data-testid="factura-display-item"
                    >
                      <span className="flex-1">
                        {item.concepto}{' '}
                        <span className="text-muted-foreground">× {item.cantidad}</span>
                      </span>
                      <span className="font-mono">{money(item.subtotal)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <hr className="border-border" />

            {/* === Sección: Segregación de valores (impuestos + totales) === */}
            <section className="space-y-2" data-testid="factura-display-totales">
              <h2 className="text-sm font-semibold text-muted-foreground">
                {t('facturacion:display.totales', { defaultValue: 'Totales' })}
              </h2>
              <dl className="space-y-1 text-sm">
                <div className="flex justify-between">
                  <dt>{t('facturacion:display.subtotal', { defaultValue: 'Subtotal' })}</dt>
                  <dd className="font-mono" data-testid="factura-display-subtotal">
                    {money(f.subtotal)}
                  </dd>
                </div>
                {f.descuento && f.descuento > 0 && (
                  <div className="flex justify-between">
                    <dt>{t('facturacion:display.descuento', { defaultValue: 'Descuento' })}</dt>
                    <dd className="font-mono">− {money(f.descuento)}</dd>
                  </div>
                )}
                {/* Impuestos aplicados — segregación (DEC-SUC-24) */}
                {f.impuestos.map((imp) => (
                  <div
                    key={imp.uuid}
                    className="flex justify-between text-muted-foreground"
                    data-testid="factura-display-impuesto"
                  >
                    <dt>
                      {imp.nombre_impuesto ?? 'Impuesto'}{' '}
                      {imp.porcentaje_aplicado !== null &&
                        imp.porcentaje_aplicado !== undefined &&
                        `(${(imp.porcentaje_aplicado * 100).toFixed(2)}%)`}
                    </dt>
                    <dd className="font-mono">{money(imp.valor)}</dd>
                  </div>
                ))}
                <div className="flex justify-between border-t border-border pt-1 text-base font-semibold">
                  <dt>{t('facturacion:display.total', { defaultValue: 'TOTAL' })}</dt>
                  <dd className="font-mono" data-testid="factura-display-total">
                    {money(f.total)}
                  </dd>
                </div>
              </dl>
            </section>

            <hr className="border-border" />

            {/* === Sección: Medio de pago === */}
            <section
              className="space-y-1"
              data-testid="factura-display-mediopago"
            >
              <h2 className="text-sm font-semibold text-muted-foreground">
                {t('facturacion:display.medioPago', { defaultValue: 'Medio de pago' })}
              </h2>
              <p className="text-base font-medium capitalize">{f.medio_pago}</p>
              {f.medio_pago === 'efectivo' && f.monto_recibido_cents !== null && f.monto_recibido_cents !== undefined && (
                <div className="flex justify-between text-sm">
                  <span>{t('facturacion:display.recibido', { defaultValue: 'Recibido' })}</span>
                  <span className="font-mono">{money(f.monto_recibido_cents)}</span>
                </div>
              )}
              {f.medio_pago === 'efectivo' && f.vuelto_cents !== null && f.vuelto_cents !== undefined && f.vuelto_cents > 0 && (
                <div className="flex justify-between text-sm">
                  <span>{t('facturacion:display.vueltos', { defaultValue: 'Vueltos' })}</span>
                  <span className="font-mono">{money(f.vuelto_cents)}</span>
                </div>
              )}
              {f.medio_pago === 'datafono' && f.voucher && (
                <p className="text-sm">
                  Voucher: <span className="font-mono">{f.voucher}</span>
                </p>
              )}
            </section>

            {/* === Sección: FE estado DIAN (when assigned) === */}
            {f.factura_electronica && (
              <>
                <hr className="border-border" />
                <section
                  className="space-y-1"
                  data-testid="factura-display-fe"
                >
                  <h2 className="text-sm font-semibold text-muted-foreground">
                    {t('facturacion:display.facturaElectronica', {
                      defaultValue: 'Factura electrónica',
                    })}
                  </h2>
                  <p className="text-base font-medium">
                    {f.factura_electronica.prefijo ?? ''}
                    {f.factura_electronica.consecutivo ?? '—'}
                  </p>
                  <p
                    className="text-sm capitalize"
                    data-estado={f.factura_electronica.estado_dian}
                  >
                    {f.factura_electronica.estado_dian}
                  </p>
                  {f.factura_electronica.cufe && (
                    <p className="text-xs font-mono break-all">
                      CUFE: {f.factura_electronica.cufe}
                    </p>
                  )}
                </section>
              </>
            )}

            <DialogFooter>
              <Button
                type="button"
                onClick={onClose}
                data-testid="factura-display-cerrar"
              >
                {t('common:close', { defaultValue: 'Cerrar' })}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}