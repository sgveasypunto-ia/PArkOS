/**
 * UX1 — scopes the SWR cache to one operator session.
 *
 * Every user-scoped hook (sesion activa, mi-turno, ocupación, ingresos,
 * alertas...) shares the SWR cache, which outlives the auth store. After a
 * logout ("Finalizar y salir", token expiry, manual) + login in the same tab
 * the CLOSED turno was served from cache and the dedupe window suppressed the
 * `sesion/me` revalidation. All logout paths end in `useAuthStore.clear()`,
 * so a token going non-null -> null swaps in a brand-new SWR provider (empty
 * cache, empty dedupe state). A token rotation keeps the cache.
 */
import { useState, type ReactNode } from 'react';
import { SWRConfig } from 'swr';

import { useAuthStore } from '@parkos/ui-kit/store';

const freshCache = () => new Map();

export function SwrSessionScope({ children }: { children: ReactNode }): JSX.Element {
  const token = useAuthStore((s) => s.accessToken);
  const [prevToken, setPrevToken] = useState(token);
  const [generation, setGeneration] = useState(0);

  if (token !== prevToken) {
    setPrevToken(token);
    if (prevToken && !token) setGeneration((g) => g + 1);
  }

  return (
    <SWRConfig key={generation} value={{ provider: freshCache }}>
      {children}
    </SWRConfig>
  );
}
