/**
 * <StatusBar /> — F2.3 (T6, DEC-UPD-12).
 *
 * Polls `window.bridge.apiStatus.get()` every 30 s and renders one of
 * three accessible states:
 *   - 🟢 API OK          (ok:true, latency_ms <= 1000)
 *   - 🟡 API lento       (ok:true, latency_ms >  1000)
 *   - 🔴 Sin API         (ok:false)
 *
 * F11.1 (HU-F11.1, AD-4, DA-F11.1-2 single source of truth): the poll
 * path now also drives `apiStatusStore.incrementFailure()` on every
 * rejection and `apiStatusStore.reset()` on every resolve. The
 * `<LocalApiDownBanner />` reads `selectApiStatusDown` from this same
 * store — no component decides the "API is down" signal
 * independently. Visual output (chip text + colors) is unchanged.
 *
 * Accessibility:
 *   - `role="status"` + `aria-live="polite"` + `aria-atomic="true"`
 *     so screen readers announce transitions without interrupting
 *     the operator (RNF-022 WCAG 2.1 AA).
 *   - De-duplication: consecutive identical states never re-announce.
 *   - Debounce 2 s between distinct announcements.
 */
import { useEffect, useRef, useState } from 'react';

import { useApiStatusStore } from '../../state/apiStatusStore';
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

export function StatusBar(): JSX.Element | null {
  // F2.3 + dev: StatusBar solo se renderiza dentro de Electron (donde
  // window.bridge existe). En navegador (Vite standalone para dev/test) NO
  // se muestra — evita ruido visual tipo "🔴 Sin API" + "Fase 2 en construcción"
  // cuando la app corre fuera de Electron.
  //
  // React Hooks must run unconditionally, in the same order, on every
  // render (rules-of-hooks). Bailing out with `return null` BEFORE the
  // hook calls below meant `useState`/`useRef`/`useEffect` were skipped
  // whenever `inElectron` was false, and would run whenever it was true —
  // if the SAME mounted instance ever re-rendered with a different
  // `inElectron` value (e.g. a parent toggling `window.bridge` without
  // unmounting `<StatusBar />`), React would throw "Rendered fewer hooks
  // than expected". Hooks now always run; the `inElectron` bail-out moved
  // to the end, after every hook has been called.
  const inElectron = typeof window !== 'undefined' && typeof (window as { bridge?: unknown }).bridge !== 'undefined';

  const [state, setState] = useState<StatusBarState>({
    apiStatus: null,
    display: 'offline',
    lastAnnouncedState: null,
    lastAnnouncedAt: 0,
  });

  const cancelledRef = useRef(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!inElectron) return;

    cancelledRef.current = false;

    const tick = async (): Promise<void> => {
      // F11.1 (HU-F11.1): route the bridge read through apiStatusStore
      // so the LocalApiDownBanner threshold is a single source of truth.
      let apiStatus: ApiStatus | null = null;
      try {
        apiStatus = (await window.bridge.apiStatus.get()) as ApiStatus;
        useApiStatusStore.getState().reset();
      } catch {
        useApiStatusStore.getState().incrementFailure();
      }
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
  }, [inElectron]);

  if (!inElectron) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      aria-atomic="true"
      aria-label={displayAriaLabel(state.display)}
      data-testid="status-bar"
      data-status={state.display}
      // F31.3 rediseño: la clase `status-bar` nunca tuvo una regla CSS
      // asociada (grep confirma cero matches en el proyecto) — el chip se
      // renderizaba sin estilos, aunque `App.tsx`/`Dashboard.tsx` ya
      // asumían ~2rem de alto para esta franja en sus cálculos de
      // `min-h-[calc(100dvh-...)]`. `h-8` = 2rem exactos, así que el alto
      // real ahora coincide con esa suposición en vez de contradecirla.
      // Tokens de marca (--muted/--border/--foreground vía Tailwind) y la
      // escala tipográfica fluida existente (`text-label`, tokens.css) —
      // sin valores sueltos.
      className="status-bar flex h-8 w-full items-center justify-center gap-1 truncate border-b border-border/40 bg-muted/60 px-3 text-center text-label font-medium text-muted-foreground"
    >
      {displayText(state.display)}
    </div>
  );
}