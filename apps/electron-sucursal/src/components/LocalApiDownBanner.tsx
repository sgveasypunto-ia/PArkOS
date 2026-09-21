/**
 * `<LocalApiDownBanner />` — sticky hard-fault banner shown when the
 * local API has failed `LOCAL_API_DOWN_THRESHOLD` (3) consecutive polls
 * (REQ-OPS-172 + AD-3 + DA-F11.1-6 separation contract).
 *
 * Distinctness contract (DA-F11.1-1 + DA-F11.1-6):
 *   - DIFFERENT component file from `<SyncBanner />` and `<StatusBar />`.
 *   - DIFFERENT role: `alert` (assertive live region) — NOT `status`.
 *   - DIFFERENT aria-label: `"Estado de API local"` — the SC reader nav
 *     surfaces it as a distinct fault.
 *   - DIFFERENT i18n keys: `localApiDown.*` namespace — never overlaps
 *     with `<SyncBanner />`'s `syncBanner.*` keys.
 *
 * Persistence:
 *   The banner mounts only when `selectApiStatusDown(state) === true`
 *   and unmounts (within one render frame) the moment `state.reset()`
 *   fires. It has NO manual dismiss — the local API coming back online
 *   is the only legitimate dismiss path.
 */
import { useTranslation } from 'react-i18next';
import { CircleAlert } from 'lucide-react';

import {
  selectApiStatusDown,
  useApiStatusStore,
} from '../state/apiStatusStore';

export function LocalApiDownBanner(): JSX.Element | null {
  const { t } = useTranslation('sync');
  const down = useApiStatusStore(selectApiStatusDown);

  if (!down) return null;

  return (
    <div
      role="alert"
      aria-live="assertive"
      aria-atomic="true"
      aria-label="Estado de API local"
      data-testid="local-api-down-banner"
      data-state="down"
      className="flex w-full items-center gap-2 bg-destructive px-3 py-2 text-sm font-semibold text-destructive-foreground"
    >
      <CircleAlert className="h-4 w-4" aria-hidden="true" />
      <span>{t('localApiDown.copy')}</span>
      <span className="ml-auto text-xs opacity-90">{t('localApiDown.cta')}</span>
    </div>
  );
}
