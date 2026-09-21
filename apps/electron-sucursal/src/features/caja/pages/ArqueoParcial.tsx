/**
 * `<ArqueoParcial />` — F10.1 routed page (REQ-OPS-152 / AD-1).
 *
 * The routed page `/caja/arqueo-parcial` WRAPS the existing
 * `<ArqueoSheet>` drawer (instead of replacing it). On mount, the
 * page:
 *   1. Resolves the active `sesion` via `useSesionActiva()`.
 *   2. Fetches the live resumen via `useArqueoResumen(uuid_sucursal, fecha)`.
 *   3. Opens the `useDashboardDrawerStore` to `'arqueo'` so the
 *      existing `<ArqueoSheet>` mounts with the right `open` flag
 *      (the Sheet is bound to the store, NOT the route).
 *   4. Renders `<ArqueoSheet>` inline with `uuid_sesion` and
 *      `expected` so the form can show live diferencia feedback.
 *
 * The page preserves the F4 hotkey + sidebar anchor on Dashboard by
 * NOT competing with `DrawerHost` — when on the routed page,
 * DrawerHost is unmounted (different route); when on Dashboard,
 * DrawerHost mounts the drawer without this page rendering.
 *
 * REQ-OPS-154 (AD-4) — the expected values come from the
 * server-computed resumen; the renderer MUST NOT compute `esperado`
 * from local `factura_pagos` cache (drift anchor DA-6 — the
 * `fn_factura_pagos_inmutable` trigger blocks any UPDATE).
 */
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';

import { Skeleton } from '@/components/ui/skeleton';

import { useAuth } from '@parkos/ui-kit/hooks';

import { useSesionActiva } from '../hooks/useSesionActiva';
import { useArqueoResumen } from '../hooks/useArqueo';
import { useDashboardDrawerStore } from '@/store/dashboardDrawerStore';
import { ArqueoSheet } from '../components/ArqueoSheet';

/** Anchor id used when this page programmatically opens the drawer. */
const ROUTED_PAGE_ANCHOR_ID = 'arqueo-routed-page';

export function ArqueoParcial(): JSX.Element {
  const { t } = useTranslation('caja');
  const { sucursal } = useAuth();
  const { sesion, isLoading: isSesionLoading } = useSesionActiva();
  const openDrawer = useDashboardDrawerStore((s) => s.open);
  const closeDrawer = useDashboardDrawerStore((s) => s.close);

  const uuid_sucursal = sucursal?.uuid ?? null;
  const fecha = new Date().toISOString().slice(0, 10);
  const { data: resumen } = useArqueoResumen(
    sesion && uuid_sucursal ? uuid_sucursal : null,
    sesion && uuid_sucursal ? fecha : null,
  );

  // On mount, open the ArqueoSheet drawer via the store so the
  // existing `<ArqueoSheet>` (mounted inline below) renders with
  // `open=true`. On unmount, close it so the next route doesn't
  // inherit the open state. The anchor id is the page element so
  // focus-restore returns to the route outlet on close.
  useEffect(() => {
    if (!sesion) return;
    openDrawer('arqueo', ROUTED_PAGE_ANCHOR_ID);
    return () => {
      closeDrawer();
    };
  }, [sesion, openDrawer, closeDrawer]);

  // ── No active session: render the F3.3 fallback (REQ-OPS-152 S2). ──
  if (isSesionLoading) {
    return (
      <Skeleton
        className="h-32 w-full"
        data-testid="arqueo-parcial-skeleton"
      />
    );
  }

  if (!sesion) {
    return (
      <section
        aria-label={t('arqueoParcial', { defaultValue: 'Arqueo parcial' })}
        className="space-y-2 p-4"
        data-testid="arqueo-parcial-no-session"
      >
        <h2 className="text-lg font-semibold">
          {t('arqueoParcial', { defaultValue: 'Arqueo parcial' })}
        </h2>
        <p className="text-sm text-muted-foreground" role="status">
          {t('arqueo.fallback.noSession', {
            defaultValue:
              'Necesitás abrir un turno antes de poder hacer un arqueo parcial.',
          })}
        </p>
      </section>
    );
  }

  // ── Active session: mount the existing `<ArqueoSheet>` with ──
  // ── `uuid_sesion` and the live `expected` resumen.           ──
  return (
    <section
      aria-label={t('arqueoParcial', { defaultValue: 'Arqueo parcial' })}
      data-testid="arqueo-parcial-page"
    >
      <ArqueoSheet
        uuid_sesion={sesion.uuid}
        expected={
          resumen
            ? {
                valor_esperado_efectivo: resumen.total_efectivo_cop,
                valor_esperado_datafono: resumen.total_datafono_cop,
                // TOLERANCIA-EFECTIVO: the resolver ships a per-sucursal
                // tolerance; we fall back to a sensible default when
                // the resumen endpoint does not include it. F10.1 spec
                // (REQ-OPS-154) names the constant as
                // `configuracion_tolerancias.tolerancia_efectivo` —
                // the GET resumen response includes it.
                tolerancia_efectivo: 1_000,
                tolerancia_datafono: 500,
              }
            : null
        }
      />
    </section>
  );
}
