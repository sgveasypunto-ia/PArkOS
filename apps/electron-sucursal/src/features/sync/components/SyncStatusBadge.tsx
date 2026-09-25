/**
 * `<SyncStatusBadge />` — real-time sync-to-cloud indicator, mounted
 * inside the Dashboard navbar (REQ-OPS-171, AD-3/AD-4/AD-5 realineados
 * 2026-09-24 por directiva del operador: la funcionalidad dejó de ser
 * un banner de arriba de la página y ahora vive como el badge
 * `dashboard-online` del header, con el detalle en un tooltip Radix).
 *
 * Reemplaza `<SyncBanner />` (eliminado — sin más consumidores tras
 * este cambio) y el shim `<SyncStatusStrip />` (eliminado — anchor de
 * test legado sin propósito real).
 *
 * Visual:
 *   - Sin `data` todavía (pre-fetch) → estado neutro (zinc), tooltip
 *     "cargando" — evita mostrar un color engañoso antes de conocer
 *     el estado real (mismo criterio que el `<SyncBanner />` original,
 *     que directamente no renderizaba nada pre-fetch).
 *   - `online` (lag_seg <= 60, pendientes <= 5) → emerald.
 *   - `lagging` (60 < lag_seg <= 3600 OR pendientes > 5) → amber.
 *   - `offline` (lag_seg > 3600 OR pendientes > 100) → red.
 *   - `never_synced` (lag_seg IS NULL) → neutral zinc, NOT red (avoids
 *     alarm fatigue on fresh installs).
 *
 * El texto visible del badge se mantiene genérico (`common:online`,
 * mismo copy que ya existía) — el color del punto/fondo y el tooltip
 * son lo que ahora refleja el estado real, por directiva del operador.
 *
 * Accessibility:
 *   - El tooltip (hover/focus, Radix) expone el detalle bajo demanda.
 *   - Transiciones de estado se anuncian a lectores de pantalla vía un
 *     `<span className="sr-only" role="status" aria-live="polite">`
 *     SEPARADO del badge visible — un tooltip por sí solo no anuncia
 *     cambios de estado en el momento en que ocurren (RNF-022 WCAG
 *     2.1 AA). Debounce de 2 s — verbatim patrón F2.3
 *     `StatusBar.tsx:90-100` / `SyncBanner.tsx` original.
 *
 * The component subscribes to `useSyncEstado(uuid_sucursal)` which
 * already configures `refreshInterval: 30_000` per plan.md §HU-F11.1.
 */
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { cva } from 'class-variance-authority';

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

import { useSyncEstado } from '../hooks/useSyncEstado';
import { deriveSyncState, type SyncState } from '../deriveSyncState';

/** Visual state for the badge: a real `SyncState`, or `null` while the
 *  first `/sync/estado` response hasn't landed yet. */
type BadgeState = SyncState | null;

const syncBadgeVariants = cva(
  'ml-auto hidden items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium shadow-apple-sm lg:inline-flex',
  {
    variants: {
      state: {
        online: 'border-emerald-200/60 bg-emerald-50/80 text-emerald-700',
        lagging: 'border-amber-200/60 bg-amber-50/80 text-amber-700',
        offline: 'border-red-200/60 bg-red-50/80 text-red-700',
        never_synced: 'border-zinc-200/60 bg-zinc-50/80 text-zinc-700',
      } satisfies Record<SyncState, string>,
    },
  },
);

const syncDotVariants = cva('h-2 w-2 rounded-full', {
  variants: {
    state: {
      online: 'bg-emerald-500',
      lagging: 'bg-amber-500',
      offline: 'bg-red-500',
      never_synced: 'bg-zinc-400',
    } satisfies Record<SyncState, string>,
  },
});

/** Neutral (zinc) visual reused both for the confirmed `never_synced`
 *  state and for the pre-fetch `null` state — both mean "no positive
 *  confirmation of a healthy sync yet". */
function visualState(state: BadgeState): SyncState {
  return state ?? 'never_synced';
}

function labelKeyFor(state: SyncState): string {
  switch (state) {
    case 'online':
      return 'syncBanner.online';
    case 'lagging':
      return 'syncBanner.lagging';
    case 'offline':
      return 'syncBanner.offline';
    case 'never_synced':
      return 'syncBanner.neverSynced';
  }
}

const ANNOUNCE_DEBOUNCE_MS = 2_000;

interface AnnouncedTracker {
  state: SyncState | null;
  lastAnnouncedAt: number;
}

export interface SyncStatusBadgeProps {
  uuid_sucursal: string | null;
}

export function SyncStatusBadge({ uuid_sucursal }: SyncStatusBadgeProps): JSX.Element {
  const { t } = useTranslation(['sync', 'common']);
  const { data } = useSyncEstado(uuid_sucursal);

  const state: BadgeState = data ? deriveSyncState(data) : null;

  // Mirror the F2.3 StatusBar / original SyncBanner announce-on-transition
  // pattern: state (not a ref) so the sr-only span reflects the announced
  // value on the same render frame the transition lands.
  const [announced, setAnnounced] = useState<AnnouncedTracker>({
    state: null,
    lastAnnouncedAt: 0,
  });

  useEffect(() => {
    if (state === null) return;
    setAnnounced((prev) => {
      const now = Date.now();
      const shouldAnnounce =
        prev.state !== state && now - prev.lastAnnouncedAt > ANNOUNCE_DEBOUNCE_MS;
      if (!shouldAnnounce) return prev;
      return { state, lastAnnouncedAt: now };
    });
  }, [state]);

  const dotState = visualState(state);
  const announcedState = announced.state ?? state;

  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span data-testid="dashboard-online" data-state={state ?? 'loading'} className={syncBadgeVariants({ state: dotState })}>
            <span aria-hidden className={syncDotVariants({ state: dotState })} />
            {t('common:online', { defaultValue: 'Online' })}
          </span>
        </TooltipTrigger>
        <TooltipContent>
          {state === null ? (
            t('common:loading')
          ) : (
            <>
              {t(labelKeyFor(state))}
              {data && data.lag_seg !== null && (
                <span data-testid="sync-banner-lag">
                  {' '}
                  {data.lag_seg}s · {data.pendientes} {t('sync:syncBanner.pendientes')}
                </span>
              )}
            </>
          )}
        </TooltipContent>
      </Tooltip>
      {state !== null && (
        <span
          className="sr-only"
          role="status"
          aria-live="polite"
          aria-atomic="true"
          data-testid="sync-badge-announcer"
          data-announced-state={announcedState}
        >
          {announcedState && t(labelKeyFor(announcedState))}
        </span>
      )}
    </TooltipProvider>
  );
}
