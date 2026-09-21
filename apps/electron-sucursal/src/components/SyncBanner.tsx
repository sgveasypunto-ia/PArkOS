/**
 * `<SyncBanner />` — top-of-page sync-to-cloud health banner
 * (REQ-OPS-171, AD-3, AD-4). Mounted globally in `App.tsx` per AD-5.
 *
 * Visual:
 *   - `online` (lag_seg <= 60, pendientes <= 5) → emerald CVA variant.
 *   - `lagging` (60 < lag_seg <= 3600 OR pendientes > 5) → amber.
 *   - `offline` (lag_seg > 3600 OR pendientes > 100) → red.
 *   - `never_synced` (lag_seg IS NULL) → neutral zinc badge, NOT red
 *     (avoids alarm fatigue on fresh installs).
 *
 * Accessibility:
 *   - `role="status"` + `aria-live="polite"` + `aria-atomic="true"`
 *     (screen-reader announces transitions without interrupting the
 *     operator; RNF-022 WCAG 2.1 AA).
 *   - Distinct `aria-label="Estado de sincronización hacia la nube"`
 *     so screen-reader nav does not confuse this banner with
 *     `<StatusBar />` or `<LocalApiDownBanner />` (DA-F11.1-6).
 *   - Announce only on state transition via `lastAnnouncedState`
 *     state + 2 s debounce — verbatim F2.3 `StatusBar.tsx:90-100`
 *     pattern (state, not ref, so the DOM reflects the announced
 *     state on the same render frame the transition lands).
 *
 * The component subscribes to `useSyncEstado(uuid_sucursal)` which
 * already configures `refreshInterval: 30_000` per plan.md §F11.1.
 */
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CloudOff, Cloud, CloudFog, CircleDashed } from 'lucide-react';
import { cva, type VariantProps } from 'class-variance-authority';

import { useSyncEstado } from '../features/sync/hooks/useSyncEstado';
import { deriveSyncState, type SyncState } from '../features/sync/deriveSyncState';

const syncBannerVariants = cva(
  'flex w-full items-center gap-2 px-3 py-1.5 text-sm font-medium transition-colors',
  {
    variants: {
      state: {
        online: 'bg-emerald-500 text-white',
        lagging: 'bg-amber-500 text-white',
        offline: 'bg-red-500 text-white',
        never_synced: 'bg-zinc-400 text-white',
      } satisfies Record<SyncState, string>,
    },
    defaultVariants: { state: 'never_synced' },
  },
);

type SyncBannerVariants = VariantProps<typeof syncBannerVariants>;

export interface SyncBannerProps {
  uuid_sucursal: string | null;
}

const ANNOUNCE_DEBOUNCE_MS = 2_000;

interface AnnouncedTracker {
  state: SyncState | null;
  lastAnnouncedAt: number;
}

export function SyncBanner({ uuid_sucursal }: SyncBannerProps): JSX.Element | null {
  const { t } = useTranslation('sync');
  const { data } = useSyncEstado(uuid_sucursal);

  // Derive the visual state. Pre-fetch we render nothing (avoids a
  // flash of "never_synced" before the first /sync/estado response).
  const state: SyncState | null = data ? deriveSyncState(data) : null;

  // Mirror the F2.3 StatusBar announce-on-transition pattern. We use
  // STATE here (not a ref) so the DOM reflects the announced value
  // on the same render frame the transition lands — see F2.3
  // StatusBar.tsx:90-100 for the verbatim reference.
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

  if (state === null) return null;

  const Icon = pickIcon(state);
  const labelKey = labelKeyFor(state);
  const announcedState = announced.state ?? state;

  return (
    <div
      role="status"
      aria-live="polite"
      aria-atomic="true"
      aria-label="Estado de sincronización hacia la nube"
      data-testid="sync-banner"
      data-state={state}
      data-announced-state={announcedState}
      className={syncBannerVariants({ state: state as SyncBannerVariants['state'] })}
    >
      <Icon className="h-4 w-4" aria-hidden="true" />
      <span>{t(labelKey)}</span>
      {data && data.lag_seg !== null && (
        <span className="ml-auto text-xs opacity-80" data-testid="sync-banner-lag">
          {data.lag_seg}s · {data.pendientes} {t('syncBanner.pendientes')}
        </span>
      )}
    </div>
  );
}

function pickIcon(state: SyncState): typeof Cloud {
  switch (state) {
    case 'online':
      return Cloud;
    case 'lagging':
      return CloudFog;
    case 'offline':
      return CloudOff;
    case 'never_synced':
      return CircleDashed;
  }
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
