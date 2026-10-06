/**
 * `useGoBack` — "Volver" that returns to the screen immediately before the
 * current one (PT-1), keeping the previous screen's URL (and therefore its
 * querystring: filters/tab) instead of jumping to a fixed route.
 *
 * `location.key === 'default'` means the current entry is the first one of
 * this history stack (deep link, refresh, new tab): there is no previous
 * in-app screen, so it falls back to `fallbackTo` (the parent list).
 */
import { useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

export function useGoBack(fallbackTo: string): () => void {
  const navigate = useNavigate();
  const location = useLocation();
  const hasInternalHistory = location.key !== 'default';
  return useCallback(() => {
    if (hasInternalHistory) {
      navigate(-1);
    } else {
      navigate(fallbackTo, { replace: true });
    }
  }, [hasInternalHistory, navigate, fallbackTo]);
}
