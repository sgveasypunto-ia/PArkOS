/**
 * `<AlertasSheet />` — bottom sheet con el panel de alertas de la sucursal.
 *
 * Antes `<AlertasPanel />` vivía inline y permanente en el dashboard
 * (chips de filtro + lista larga) y empujaba / tapaba la zona de
 * operación (placa, vehículos dentro). Ahora el panel sólo se monta cuando
 * el operador abre este sheet desde `<AlertasTrigger />` (footer de cupos).
 *
 * Mounted via `<DrawerHost>` when `useDashboardDrawerStore.openDrawer ===
 * 'alertas'` (single-drawer invariant, REQ-OPS-138). Esc / overlay / X
 * cierran vía `close()`; el foco vuelve al trigger (Radix FocusScope).
 */
import { useTranslation } from 'react-i18next';

import { AlertasPanel } from '../../../components/AlertasPanel';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { useAuth } from '@parkos/ui-kit/hooks';
import { useDashboardDrawerStore } from '@/store/dashboardDrawerStore';

import { useAlertas } from '../hooks/useAlertas';

export function AlertasSheet(): JSX.Element {
  const { t } = useTranslation(['alertas']);
  const { sucursal } = useAuth();
  const uuid_sucursal = sucursal?.uuid ?? null;
  const openDrawer = useDashboardDrawerStore((s) => s.openDrawer);
  const close = useDashboardDrawerStore((s) => s.close);
  // Misma key SWR que el trigger y el panel → dedupe, sin polling extra.
  const { openAlertsCount } = useAlertas(uuid_sucursal);

  return (
    <Sheet
      open={openDrawer === 'alertas'}
      onOpenChange={(next) => {
        if (!next) close();
      }}
    >
      <SheetContent
        side="bottom"
        data-testid="alertas-sheet"
        // Radix enlaza `aria-labelledby` a su propio id; el título conserva el
        // id histórico del panel, así que se declara explícito.
        aria-labelledby="alertas-panel-title"
        className="flex max-h-[70dvh] flex-col gap-4"
      >
        <SheetHeader className="pr-12">
          <div className="flex items-center gap-2">
            <SheetTitle id="alertas-panel-title">
              {t('alertas:dashboard.title', { defaultValue: 'Alertas de la sucursal' })}
            </SheetTitle>
            <span
              className="rounded-full bg-muted px-2 py-0.5 text-xs font-semibold text-muted-foreground"
              data-testid="open-alerts-count"
              aria-live="polite"
            >
              {openAlertsCount}
            </span>
          </div>
          <SheetDescription className="sr-only">
            {t('alertas:sheet.descripcion', {
              defaultValue: 'Alertas abiertas de la sucursal, con filtros por severidad y tipo.',
            })}
          </SheetDescription>
        </SheetHeader>
        <div className="min-h-0 flex-1 overflow-y-auto" data-testid="alertas-sheet-body">
          <AlertasPanel uuid_sucursal={uuid_sucursal} embedded />
        </div>
      </SheetContent>
    </Sheet>
  );
}
