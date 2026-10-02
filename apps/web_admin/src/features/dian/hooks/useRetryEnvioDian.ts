/**
 * `useRetryEnvioDian` -- mutation hook for the HU-F20.5 "Reintentar"
 * action (`POST /api/v1/facturacion/factura-electronica/{uuid}/reintentar`,
 * see `envioDianApi.ts`'s docblock for why this is the real endpoint).
 *
 * RIESGO-ADM-09 UX mitigation: `trigger()` marks the target
 * `uuidFacturaElectronica` as "retrying" SYNCHRONOUSLY, before the
 * `await`, so a caller's disabled-state render lands before the network
 * round-trip resolves -- a double-click can't fire a second request
 * through this hook's own caller. This is defense in depth on TOP of the
 * backend+fetch-layer's existing `Idempotency-Key` protection (see
 * `envioDianApi.ts` for the full citation trail), not a replacement for
 * it.
 *
 * Keyed by `uuidFacturaElectronica` (not a single boolean) so one hook
 * instance can back a whole table of rows (`<DianQueueTable />`) without
 * one row's retry disabling every other row's button.
 *
 * On success the mark is intentionally NOT cleared -- the retried envio
 * is no longer `rechazado` once the caller refetches, so the real gate
 * (`estado === 'rechazado'`) naturally re-disables the button; keeping
 * the mark in the meantime guards the gap before that refetch lands. On
 * failure the mark IS cleared so the admin isn't stuck unable to retry
 * after a transient error.
 */
import { useState } from 'react';

import { retryEnvioDian } from '../api/envioDianApi';
import type { EnvioDianRetryRead } from '../api/envioDianSchema';

export interface UseRetryEnvioDianReturn {
  trigger: (uuidFacturaElectronica: string) => Promise<EnvioDianRetryRead | undefined>;
  isRetrying: (uuidFacturaElectronica: string) => boolean;
  error: Error | undefined;
  data: EnvioDianRetryRead | undefined;
}

export function useRetryEnvioDian(): UseRetryEnvioDianReturn {
  const [retrying, setRetrying] = useState<ReadonlySet<string>>(new Set<string>());
  const [error, setError] = useState<Error | undefined>(undefined);
  const [data, setData] = useState<EnvioDianRetryRead | undefined>(undefined);

  function markRetrying(key: string): void {
    setRetrying((prev) => new Set(prev).add(key));
  }
  function unmarkRetrying(key: string): void {
    setRetrying((prev) => {
      const next = new Set(prev);
      next.delete(key);
      return next;
    });
  }

  async function trigger(uuidFacturaElectronica: string): Promise<EnvioDianRetryRead | undefined> {
    // Synchronous, before any `await` -- the caller's next render already
    // sees `isRetrying(uuidFacturaElectronica) === true`.
    markRetrying(uuidFacturaElectronica);
    setError(undefined);
    try {
      const result = await retryEnvioDian(uuidFacturaElectronica);
      setData(result);
      return result;
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Error desconocido'));
      unmarkRetrying(uuidFacturaElectronica);
      return undefined;
    }
  }

  return {
    trigger,
    isRetrying: (uuidFacturaElectronica: string) => retrying.has(uuidFacturaElectronica),
    error,
    data,
  };
}
