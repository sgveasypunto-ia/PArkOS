/**
 * <StatusBar /> — F2.3 (T6, DEC-UPD-12).
 *
 * Polls `window.bridge.apiStatus.get()` every 30 s and renders one of
 * three accessible states:
 *   - 🟢 API OK          (ok:true, latency_ms <= 1000)
 *   - 🟡 API lento       (ok:true, latency_ms >  1000)
 *   - 🔴 Sin API         (ok:false)
 *
 * Accessibility:
 *   - `role="status"` + `aria-live="polite"` + `aria-atomic="true"`
 *     so screen readers announce transitions without interrupting
 *     the operator (RNF-022 WCAG 2.1 AA).
 *   - De-duplication: consecutive identical states never re-announce.
 *   - Debounce 2 s between distinct announcements.
 */
import { useEffect, useRef, useState } from 'react';

import type { ApiStatus } from '../../../electron/bridge';

export type StatusBarDisplay = 'ok' | 'slow' | 'offline';

export const POLL_INTERVAL_MS = 30_000;
export const ANNOUNCE_DEBOUNCE_MS = 2_000;
export const SLOW_THRESHOLD_MS = 1_000;

function deriveDisplay(status: ApiStatus | null): StatusBarDisplay {
  if (status === null) return 'offline';
  if (!status.ok) return 'offline';
  if (status.latency_ms > SLOW_THRESHOLD_MS) return 'slow';
  return 'ok';
}

function displayText(display: StatusBarDisplay): string {
  switch (display) {
    case 'ok':
      return '🟢 API OK';
    case 'slow':
      return '🟡 API lento';
    case 'offline':
      return '🔴 Sin API';
  }
}

function displayAriaLabel(display: StatusBarDisplay): string {
  switch (display) {
    case 'ok':
      return 'Conexión con el backend estable';
    case 'slow':
      return 'Conexión con el backend lenta';
    case 'offline':
      return 'Sin conexión con el backend';
  }
}

interface StatusBarState {
  apiStatus: ApiStatus | null;
  display: StatusBarDisplay;
  lastAnnouncedState: StatusBarDisplay | null;
  lastAnnouncedAt: number;
}

export function StatusBar(): JSX.Element {
  const [state, setState] = useState<StatusBarState>({
    apiStatus: null,
    display: 'offline',
    lastAnnouncedState: null,
    lastAnnouncedAt: 0,
  });

  const cancelledRef = useRef(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    cancelledRef.current = false;

    const tick = async (): Promise<void> => {
      const apiStatus = (await window.bridge.apiStatus.get()) as ApiStatus;
      if (cancelledRef.current) return;
      const display = deriveDisplay(apiStatus);
      const now = Date.now();

      setState((prev) => {
        const shouldAnnounce =
          display !== prev.lastAnnouncedState &&
          now - prev.lastAnnouncedAt > ANNOUNCE_DEBOUNCE_MS;

        return {
          apiStatus,
          display,
          lastAnnouncedState: shouldAnnounce ? display : prev.lastAnnouncedState,
          lastAnnouncedAt: shouldAnnounce ? now : prev.lastAnnouncedAt,
        };
      });
    };

    void tick();
    intervalRef.current = setInterval(() => {
      void tick();
    }, POLL_INTERVAL_MS);

    return () => {
      cancelledRef.current = true;
      if (intervalRef.current !== null) clearInterval(intervalRef.current);
    };
  }, []);

  return (
    <div
      role="status"
      aria-live="polite"
      aria-atomic="true"
      aria-label={displayAriaLabel(state.display)}
      data-testid="status-bar"
      data-status={state.display}
      className="status-bar"
    >
      {displayText(state.display)}
    </div>
  );
}