/**
 * `useVerifyChain` -- HU-F20.4 on-demand hash-chain verification sweep.
 *
 * Deliberately NOT an auto-revalidating SWR key: the spec calls for a
 * "botón Verificar" (plan.md) -- the sweep is a potentially expensive,
 * explicit admin action, not something that should re-run on every
 * mount/filter-change like `useLogTransaccional`. A plain `useState` +
 * async trigger function covers this with no extra dependency surface
 * (no `swr/mutation` import needed, and no existing hook in this repo
 * reaches for `useSWRMutation`) -- `verify()` is called directly from
 * the "Verificar" button's `onClick` in `HashChainVerify.tsx`.
 */
import { useState } from 'react';

import { fetchVerifyChain } from '../api/auditoriaApi';
import type { VerifyChainQuery, VerifyChainResponse } from '../api/auditoriaSchema';

export interface UseVerifyChainReturn {
  result: VerifyChainResponse | null;
  isLoading: boolean;
  error: Error | null;
  verify: (query: VerifyChainQuery) => Promise<void>;
  reset: () => void;
}

export function useVerifyChain(): UseVerifyChainReturn {
  const [result, setResult] = useState<VerifyChainResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  async function verify(query: VerifyChainQuery): Promise<void> {
    setIsLoading(true);
    setError(null);
    try {
      const resp = await fetchVerifyChain(query);
      setResult(resp);
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
      setResult(null);
    } finally {
      setIsLoading(false);
    }
  }

  function reset(): void {
    setResult(null);
    setError(null);
  }

  return { result, isLoading, error, verify, reset };
}
