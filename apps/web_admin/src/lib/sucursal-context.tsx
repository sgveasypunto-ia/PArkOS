/**
 * SucursalContext — global X-Sucursal-Context header provider for web_admin.
 *
 * - The selected UUID is mirrored to `localStorage` under
 *   `parkos.lastSelectedSucursal` so the BranchSelector choice survives
 *   a page reload (T-PR10-12, requirement §10.4).
 * - `getSucursalHeader()` is a non-React reader used by the global
 *   `parkosFetch()` wrapper (T-PR10-12) so every admin request carries
 *   the `X-Sucursal-Context` header required by `admin_views` (REQ-X2).
 * - The provider DOES NOT fetch the dashboard itself — that's the
 *   Dashboard page's job. This module only owns the selection + the
 *   side effects on switch.
 */
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
} from 'react';
import type { ReactNode } from 'react';

export const SUCURSAL_STORAGE_KEY = 'parkos.lastSelectedSucursal';

interface SucursalContextValue {
  selected: string | null;
  setSelected: (uuid: string | null) => void;
}

const SucursalContext = createContext<SucursalContextValue | null>(null);

function readInitialSelection(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.localStorage.getItem(SUCURSAL_STORAGE_KEY);
  } catch {
    return null;
  }
}

function persistSelection(uuid: string | null): void {
  if (typeof window === 'undefined') return;
  try {
    if (uuid) {
      window.localStorage.setItem(SUCURSAL_STORAGE_KEY, uuid);
    } else {
      window.localStorage.removeItem(SUCURSAL_STORAGE_KEY);
    }
  } catch {
    // localStorage may be unavailable (private mode, quota, SSR).
    // The selection still lives in memory for the current page.
  }
}

export function SucursalProvider({ children }: { children: ReactNode }) {
  const [selected, setSelectedState] = useState<string | null>(
    readInitialSelection,
  );

  const setSelected = useCallback((uuid: string | null) => {
    setSelectedState(uuid);
    persistSelection(uuid);
  }, []);

  const value = useMemo<SucursalContextValue>(
    () => ({ selected, setSelected }),
    [selected, setSelected],
  );

  return (
    <SucursalContext.Provider value={value}>{children}</SucursalContext.Provider>
  );
}

export function useSucursal(): SucursalContextValue {
  const ctx = useContext(SucursalContext);
  if (!ctx) {
    throw new Error('useSucursal must be used within a SucursalProvider');
  }
  return ctx;
}

/**
 * Read the current branch selection from `localStorage`.
 *
 * Used by the global `parkosFetch()` wrapper so the header is injected
 * without forcing every caller to be inside the React tree. Returns an
 * empty object when no branch is selected — the admin endpoint then
 * responds with the appropriate 400/403 (REQ-X2).
 */
export function getSucursalHeader(): Record<string, string> {
  const uuid = readInitialSelection();
  return uuid ? { 'X-Sucursal-Context': uuid } : {};
}
