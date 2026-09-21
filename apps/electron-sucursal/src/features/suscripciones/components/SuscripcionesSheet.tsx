/**
 * `<SuscripcionesSheet />` — HU-F9.2 + F9 side drawer for the operator.
 *
 * Bridges two existing subsystems:
 *   - `useSuscripcionesList` (F9.2) fetches the active branch's
 *     subscriptions and renders them as a compact list with state
 *     badges.
 *   - The "Nueva venta" button closes the drawer and navigates to
 *     `/suscripciones/venta` -- the existing 4-step `<Venta />`
 *     wizard (F9.1). Reusing the wizard instead of re-implementing
 *     the 4 steps keeps PagoModal, prorrateo, and the discriminated
 *     backend-error handling in one place.
 *
 * Mounted via `<DrawerHost>` when `useDashboardDrawerStore.openDrawer
 * === 'suscripciones'` (single-drawer invariant per REQ-OPS-138).
 * Focus restores to the trigger element on close per same.
 *
 * Side: right (matches PagoSheet, ArqueoSheet, IngresoSheet,
 * SalidaSheet convention).
 */
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

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

export function SuscripcionesSheet(): JSX.Element {
  const { t } = useTranslation(['suscripciones', 'common']);
  const navigate = useNavigate();
  const { sucursal } = useAuth();
  const openDrawer = useDashboardDrawerStore((s) => s.openDrawer);
  const lastAnchorId = useDashboardDrawerStore((s) => s.lastAnchorId);
  const close = useDashboardDrawerStore((s) => s.close);
  const uuid_sucursal = sucursal?.uuid ?? null;
  const { data, error, refresh } = useSuscripcionesList(uuid_sucursal);

  const open = openDrawer === 'suscripciones';

  // REQ-OPS-138 §Esc -- restore DOM focus to the sidebar anchor
  // (data-testid="sidebar-suscripciones") so keyboard users land
  // back on the trigger.
  useEffect(() => {
    if (!open && lastAnchorId) {
      document.getElementById(lastAnchorId)?.focus();
    }
  }, [open, lastAnchorId]);

  // "Nueva venta" closes the drawer first (so the wizard's
  // `<PagoModal>` mounts on /suscripciones/venta without the sheet
  // overlay still rendered, single-drawer invariant preserved), then
  // navigates. Navigation must come AFTER close() because close
  // mutates global UI state and we're already on a tick boundary;
  // order matters less than ensuring the sheet close-handler
  // completes its focus-restore before the page navigates.
  const handleNuevaVenta = (): void => {
    close();
    void refresh();
    navigate('/suscripciones/venta');
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
            {t('suscripciones:sheet.titulo', { defaultValue: 'Suscripciones' })}
          </SheetTitle>
          <SheetDescription>
            {t('suscripciones:sheet.descripcion', {
              defaultValue: 'Lista activa de suscripciones en esta sede.',
            })}
          </SheetDescription>
        </SheetHeader>

        {/* Body scrolls independently of header + footer. */}
        <div
          className="flex-1 overflow-y-auto px-4"
          data-testid="suscripciones-sheet-body"
        >
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
                        ? t('suscripciones:activa', { defaultValue: 'Activa' })
                        : t('suscripciones:vencida', { defaultValue: 'Vencida' })}
                    </span>
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {s.fecha_inicio} → {s.fecha_fin}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

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
      </SheetContent>
    </Sheet>
  );
}
