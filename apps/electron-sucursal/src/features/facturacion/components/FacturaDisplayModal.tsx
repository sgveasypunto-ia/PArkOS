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
 * Visual format (2026-09-24, operator directive): mirrors `<TiqueteModal
 * />`'s (HU-F6.2) print-preview grammar — a single monospaced, dashed-
 * bordered "ticket" box — instead of a sectioned UI card. The operator
 * sees the ingreso ticket and the pago receipt as the SAME kind of
 * document (both previews of what the 58mm thermal printer emits), not
 * two visually unrelated dialogs. Content/data-testids are unchanged
 * from the prior sectioned layout — only the container grammar changed.
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

/** Dashed separator between ticket line-groups (mirrors TiqueteModal's preview box). */
function TicketDivider(): JSX.Element {
  return <div className="mt-1 border-t border-dashed border-neutral-400 pt-1" />;
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

            {/* Ticket-preview box — same visual grammar as `<TiqueteModal
                />`'s print preview (mono font, dashed border, white
                background) so the operator reads both post-operation
                confirmations as the same kind of document. */}
            <div
              data-testid="factura-display-preview"
              aria-label={t('facturacion:display.titulo', { defaultValue: 'Factura emitida' })}
              className="mx-auto w-full max-w-sm rounded border border-dashed border-muted-foreground/40 bg-white p-3 font-mono text-xs leading-relaxed text-neutral-900 shadow-inner"
            >
              <div className="mb-1 text-center font-bold uppercase tracking-wide">
                {t('facturacion:display.titulo', { defaultValue: 'Factura emitida' })}
              </div>
              <div className="mb-1 text-center text-[11px] text-neutral-500">
                {f.numero_recibo}
              </div>

              {/* === Emisor === */}
              <div data-testid="factura-display-sucursal">
                <TicketDivider />
                <div className="font-semibold">{f.datos_sucursal.razon_social ?? '—'}</div>
                <div>
                  NIT {f.datos_sucursal.nit ?? '—'}
                  {f.datos_sucursal.regimen ? ` · ${f.datos_sucursal.regimen}` : ''}
                </div>
                {f.datos_sucursal.direccion && <div>{f.datos_sucursal.direccion}</div>}
                {f.datos_sucursal.telefono && <div>{f.datos_sucursal.telefono}</div>}
              </div>

              {/* === Cliente === */}
              <div data-testid="factura-display-cliente">
                <TicketDivider />
                {f.cliente ? (
                  <>
                    <div>
                      <span className="font-semibold">
                        {t('facturacion:display.cliente', { defaultValue: 'Cliente' })}:
                      </span>{' '}
                      {f.cliente.nombre ?? '—'}
                      {f.cliente.apellido ? ` ${f.cliente.apellido}` : ''}
                    </div>
                    <div>
                      {f.cliente.nit ?? '—'}
                      {f.cliente.dv ? `-${f.cliente.dv}` : ''}
                    </div>
                    {f.cliente.email && <div>{f.cliente.email}</div>}
                  </>
                ) : (
                  <div>
                    <span className="font-semibold">
                      {t('facturacion:display.cliente', { defaultValue: 'Cliente' })}:
                    </span>{' '}
                    {t('facturacion:display.consumidorFinal', { defaultValue: 'Consumidor final' })}
                  </div>
                )}
              </div>

              {/* === Vehículo + minutos === */}
              {f.datos_vehiculo && (
                <div data-testid="factura-display-vehiculo">
                  <TicketDivider />
                  <div className="text-sm font-bold tracking-wider">
                    {f.datos_vehiculo.placa ?? '—'}
                  </div>
                  <div data-testid="factura-display-minutos">
                    <span className="font-semibold">
                      {t('facturacion:display.tiempo', { defaultValue: 'Tiempo' })}:
                    </span>{' '}
                    {tiempoMinutos(f.datos_vehiculo.minutos)}
                  </div>
                </div>
              )}

              {/* === Líneas / items === */}
              <div data-testid="factura-display-items">
                <TicketDivider />
                {f.items.length === 0 ? (
                  <div>—</div>
                ) : (
                  f.items.map((item) => (
                    <div
                      key={item.uuid}
                      className="flex justify-between gap-2"
                      data-testid="factura-display-item"
                    >
                      {/* min-w-0 + truncate: un concepto largo no debe
                          empujar el valor fuera del ticket en 320-480px
                          (mismo patrón que Dashboard.tsx usa para filas
                          flex con contenido variable). */}
                      <span className="min-w-0 flex-1 truncate">
                        {item.concepto} × {item.cantidad}
                      </span>
                      <span className="shrink-0 tabular-nums">{money(item.subtotal)}</span>
                    </div>
                  ))
                )}
              </div>

              {/* === Segregación de valores (impuestos + totales) === */}
              <div data-testid="factura-display-totales">
                <TicketDivider />
                <div className="flex justify-between gap-2">
                  <span className="min-w-0 truncate">{t('facturacion:display.subtotal', { defaultValue: 'Subtotal' })}</span>
                  <span data-testid="factura-display-subtotal" className="shrink-0 tabular-nums">{money(f.subtotal)}</span>
                </div>
                {(f.descuento ?? 0) > 0 && (
                  <div className="flex justify-between gap-2">
                    <span className="min-w-0 truncate">{t('facturacion:display.descuento', { defaultValue: 'Descuento' })}</span>
                    <span className="shrink-0 tabular-nums">− {money(f.descuento)}</span>
                  </div>
                )}
                {f.impuestos.map((imp) => (
                  <div
                    key={imp.uuid}
                    className="flex justify-between gap-2"
                    data-testid="factura-display-impuesto"
                  >
                    <span className="min-w-0 truncate">
                      {imp.nombre_impuesto ?? 'Impuesto'}{' '}
                      {imp.porcentaje_aplicado !== null &&
                        imp.porcentaje_aplicado !== undefined &&
                        `(${(imp.porcentaje_aplicado * 100).toFixed(2)}%)`}
                    </span>
                    <span className="shrink-0 tabular-nums">{money(imp.valor)}</span>
                  </div>
                ))}
                <div className="mt-1 flex justify-between gap-2 border-t border-dashed border-neutral-400 pt-1 font-bold">
                  <span className="min-w-0 truncate">{t('facturacion:display.total', { defaultValue: 'TOTAL' })}</span>
                  <span data-testid="factura-display-total" className="shrink-0 tabular-nums">{money(f.total)}</span>
                </div>
              </div>

              {/* === Medio de pago === */}
              <div data-testid="factura-display-mediopago">
                <TicketDivider />
                <div>
                  <span className="font-semibold">
                    {t('facturacion:display.medioPago', { defaultValue: 'Medio de pago' })}:
                  </span>{' '}
                  <span className="capitalize">{f.medio_pago}</span>
                </div>
                {f.medio_pago === 'efectivo' && f.monto_recibido_cents !== null && f.monto_recibido_cents !== undefined && (
                  <div className="flex justify-between gap-2">
                    <span className="min-w-0 truncate">{t('facturacion:display.recibido', { defaultValue: 'Recibido' })}</span>
                    <span className="shrink-0 tabular-nums">{money(f.monto_recibido_cents)}</span>
                  </div>
                )}
                {f.medio_pago === 'efectivo' && f.vuelto_cents !== null && f.vuelto_cents !== undefined && f.vuelto_cents > 0 && (
                  <div className="flex justify-between gap-2">
                    <span className="min-w-0 truncate">{t('facturacion:display.vueltos', { defaultValue: 'Vueltos' })}</span>
                    <span className="shrink-0 tabular-nums">{money(f.vuelto_cents)}</span>
                  </div>
                )}
                {f.medio_pago === 'datafono' && f.voucher && (
                  <div>Voucher: {f.voucher}</div>
                )}
              </div>

              {/* === FE estado DIAN (when assigned) === */}
              {f.factura_electronica && (
                <div data-testid="factura-display-fe">
                  <TicketDivider />
                  <div className="font-semibold">
                    {f.factura_electronica.prefijo ?? ''}
                    {f.factura_electronica.consecutivo ?? '—'}
                  </div>
                  <div className="capitalize" data-estado={f.factura_electronica.estado_dian}>
                    {f.factura_electronica.estado_dian}
                  </div>
                  {f.factura_electronica.cufe && (
                    <div className="break-all text-[10px]">
                      CUFE: {f.factura_electronica.cufe}
                    </div>
                  )}
                </div>
              )}
            </div>

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
