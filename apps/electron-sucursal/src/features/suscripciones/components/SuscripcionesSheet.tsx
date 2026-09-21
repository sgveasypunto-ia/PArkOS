/**
 * `<SuscripcionesSheet />` — HU-F9.2 + F9 side drawer for the operator.
 *
 * Two-mode drawer:
 *   - `mode='list'` (default) — renders the active branch's
 *     subscriptions list with the "+ Nueva venta" CTA.
 *   - `mode='venta'` — embeds the existing 4-step `<Venta />`
 *     wizard (F9.1, REQ-OPS-176) inside the drawer body so the
 *     operator can complete a sale without leaving the side
 *     panel. The wizard renders its own "← Volver" link at the top
 *     (visible because we pass `onCancel`) which returns to the
 *     list view; on successful pago we close the drawer and
 *     revalidate the cached list (no page navigation).
 *
 * Why embed instead of route: user feedback was "el wizard debe
 * cargarse dentro de la misma pestaña lateral". The wizard's
 * PasoModal + prorrateo + discriminated backend-error handling
 * stay in one component; we just swap the default `navigate(...)`
 * fallback for the optional `onSuccess` callback. The page-route
 * Venta keeps working unchanged (no props = default behavior).
 *
 * Mounted via `<DrawerHost>` when
 * `useDashboardDrawerStore.openDrawer === 'suscripciones'` (single-
 * drawer invariant, REQ-OPS-138). Focus restores to the sidebar
 * anchor on close.
 *
 * Side: right (matches PagoSheet, ArqueoSheet, IngresoSheet,
 * SalidaSheet convention).
 */
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';

import { useAuth } from '@parkos/ui-kit/hooks';

import { useDashboardDrawerStore } from '@/store/dashboardDrawerStore';

import { useSuscripcionesList } from '../hooks/useSuscripcionesList';
import { Venta } from '../pages/Venta';

type SheetMode = 'list' | 'venta';

export function SuscripcionesSheet(): JSX.Element {
  const { t } = useTranslation(['suscripciones', 'common']);
  const { sucursal } = useAuth();
  const openDrawer = useDashboardDrawerStore((s) => s.openDrawer);
  const lastAnchorId = useDashboardDrawerStore((s) => s.lastAnchorId);
  const close = useDashboardDrawerStore((s) => s.close);
  const uuid_sucursal = sucursal?.uuid ?? null;
  const { data, error, refresh } = useSuscripcionesList(uuid_sucursal);

  const open = openDrawer === 'suscripciones';

  // Reset to list whenever the drawer opens -- otherwise a stale
  // 'venta' state from a previous session survives across show/hide
  // cycles. Keeps the entry-point behavior predictable.
  const [mode, setMode] = useState<SheetMode>('list');
  useEffect(() => {
    if (open) setMode('list');
  }, [open]);

  // REQ-OPS-138 §Esc -- restore DOM focus to the sidebar anchor
  // (data-testid="sidebar-suscripciones") so keyboard users land
  // back on the trigger.
  useEffect(() => {
    if (!open && lastAnchorId) {
      document.getElementById(lastAnchorId)?.focus();
    }
  }, [open, lastAnchorId]);

  const handleNuevaVenta = (): void => {
    setMode('venta');
  };
  const handleVolver = (): void => {
    setMode('list');
  };
  const handleVentaSuccess = (): void => {
    // Pago 2xx: close the drawer + revalidate the subscription list
    // so the new entry appears when the operator re-opens the
    // sheet on a later action. No navigation needed (we never
    // navigated away from /).
    void refresh();
    close();
  };

  return (
    <Sheet
      open={open}
      onOpenChange={(next) => {
        if (!next) close();
      }}
    >
      <SheetContent
        side="right"
        data-testid="suscripciones-sheet"
        className="flex h-full flex-col gap-4"
      >
        <SheetHeader>
          <SheetTitle>
            {mode === 'venta'
              ? t('suscripciones:sheet.tituloVenta', {
                  defaultValue: 'Nueva venta de suscripción',
                })
              : t('suscripciones:sheet.titulo', {
                  defaultValue: 'Suscripciones',
                })}
          </SheetTitle>
          <SheetDescription>
            {mode === 'list'
              ? t('suscripciones:sheet.descripcion', {
                  defaultValue: 'Lista activa de suscripciones en esta sede.',
                })
              : t('suscripciones:sheet.descripcionVenta', {
                  defaultValue:
                    'Venta de suscripción en 4 pasos. Al pagar, regresa a esta pestaña.',
                })}
          </SheetDescription>
        </SheetHeader>

        {/* Body scrolls independently of header + footer. */}
        <div
          className="flex-1 overflow-y-auto px-4"
          data-testid="suscripciones-sheet-body"
        >
          {mode === 'list' ? (
            <>
              {error && (
                <p
                  role="alert"
                  className="text-sm text-destructive"
                  data-testid="suscripciones-sheet-error"
                >
                  {t('suscripciones:error', {
                    defaultValue: 'Error al cargar suscripciones.',
                  })}
                </p>
              )}
              {data && data.length === 0 && (
                <p
                  className="text-sm text-muted-foreground"
                  data-testid="suscripciones-sheet-empty"
                >
                  {t('suscripciones:sheet.listaVacia', {
                    defaultValue: 'Sin suscripciones activas en esta sede.',
                  })}
                </p>
              )}
              {data && data.length > 0 && (
                <ul className="space-y-2" data-testid="suscripciones-sheet-list">
                  {data.map((s) => (
                    <li
                      key={s.uuid}
                      className="rounded border bg-card px-3 py-2 text-sm"
                      data-testid={`suscripciones-sheet-item-${s.placa}`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-mono uppercase">{s.placa}</span>
                        <span
                          className={
                            s.estado === 'activa'
                              ? 'text-xs text-emerald-600'
                              : 'text-xs text-muted-foreground'
                          }
                        >
                          {s.estado === 'activa'
                            ? t('suscripciones:activa', {
                                defaultValue: 'Activa',
                              })
                            : t('suscripciones:vencida', {
                                defaultValue: 'Vencida',
                              })}
                        </span>
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {s.fecha_inicio} → {s.fecha_fin}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </>
          ) : (
            /*
             * The wizard itself owns its title via the inner <h1> + the
             * "← Volver" link rendered above the wizard header when
             * onCancel is supplied (Venta line 236).
             */
            <Venta
              onSuccess={handleVentaSuccess}
              onCancel={handleVolver}
            />
          )}
        </div>

        {mode === 'list' && (
          <SheetFooter>
            <Button
              type="button"
              variant="default"
              onClick={handleNuevaVenta}
              data-testid="suscripciones-sheet-nueva-venta"
              className="w-full"
            >
              +{' '}
              {t('suscripciones:sheet.nuevaVenta', {
                defaultValue: 'Nueva venta de suscripción',
              })}
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => close()}
              data-testid="suscripciones-sheet-cancelar"
              className="w-full"
            >
              {t('common:cancel', { defaultValue: 'Cancelar' })}
            </Button>
          </SheetFooter>
        )}
      </SheetContent>
    </Sheet>
  );
}
