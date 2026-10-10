/**
 * `useBreadcrumbs.tsx` — opt-in hook + provider for the breadcrumb
 * chain rendered by `<Breadcrumb />` (see `components/chrome/Breadcrumb.tsx`).
 *
 * Mental model:
 *   - The DEFAULT chain for a route comes from `BREADCRUMB_ROUTES`
 *     (`lib/breadcrumbs.ts`), keyed off `useLocation().pathname`. The
 *     default chain is good enough for every static route (lists,
 *     dashboard, branch-scoped surfaces, etc.).
 *   - Detail pages (`UsuarioDetalle`, `SucursalDetalle`, ...) want
 *     the LAST segment to read the resource's real name (e.g.
 *     "Juan Pérez" instead of the generic "Detalle" placeholder). They
 *     opt in with `useBreadcrumbs([...])`, which REPLACES the entire
 *     chain for the lifetime of the current detail page.
 *   - The chain lives in a React context. The provider owns the
 *     override slot; detail pages mutate it via an effect; the
 *     consumer (`<Breadcrumb />`) reads it.
 *
 * Pathname-keyed override lifecycle:
 *   The provider listens to `useLocation().pathname` and clears the
 *   override on every pathname change. This is the "natural" cleanup:
 *   when the user navigates from a detail page to a list (or to a
 *   different detail page), the override is reset so the consumer
 *   falls back to the table resolution. Without this, the detail
 *   page's cleanup + the next page's setup would race (both bump
 *   the version, leaving the override either stale or double-set).
 *
 * Why the consumer's effect doesn't have a cleanup:
 *   The detail page's `useBreadcrumbs([...])` effect commits the
 *   chain on mount and re-runs only when the array CONTENTS change
 *   (via `useRef` of the latest value, deep-equal compared). No
 *   cleanup is needed because the provider clears the override on
 *   pathname change — a navigation away from a detail page
 *   re-mounts the chrome shell only if the route's parent changes,
 *   not for normal SPA navigation.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { useLocation } from 'react-router-dom';

import {
  matchBreadcrumb,
  templateToCrumb,
  type BreadcrumbEntry,
  type Crumb,
} from './breadcrumbs';
import { useSucursal } from './sucursal-context';
import { useSucursalesDirectorio } from '@/features/sucursales/hooks/useSucursalesDirectorio';

export type { Crumb, BreadcrumbEntry };

export interface ResolvedBreadcrumbs {
  /** Final chain. `null` means "do not render" (unmatched path, e.g. `/login`). */
  crumbs: Crumb[] | null;
  /** Matched entry, for tests / debug. `null` when override is active. */
  entry: BreadcrumbEntry | null;
}

const NULL_RESOLVED: ResolvedBreadcrumbs = { crumbs: null, entry: null };

interface BreadcrumbSlot {
  /** Current override array (or null). */
  override: Crumb[] | null;
  /** Commit a new override; no-op if the contents are unchanged. */
  commit: (next: Crumb[] | null) => void;
}

const BreadcrumbContext = createContext<BreadcrumbSlot | null>(null);

export interface BreadcrumbsProviderProps {
  children: ReactNode;
}

/**
 * `BreadcrumbsProvider` — owns the override slot. Clears the override
 * on every pathname CHANGE (not on the initial mount) so a stale
 * chain from a previous detail page doesn't leak onto a new route.
 * The `commit` setter dedupes by deep-equal so re-renders with the
 * same contents are free.
 *
 * Why "on change" not "on every render": effect order is children
 * first, then parents. A detail page's `useBreadcrumbs` effect runs
 * BEFORE the provider's effect, and a naive "clear on every render"
 * would erase the just-committed chain. Tracking the previous
 * pathname and only clearing on actual changes avoids the race.
 */
export function BreadcrumbsProvider({ children }: BreadcrumbsProviderProps): JSX.Element {
  const [override, setOverrideState] = useState<Crumb[] | null>(null);
  const location = useLocation();
  const pathname = location.pathname;
  const prevPathnameRef = useRef<string | null>(null);

  // Clear only on PATHNAME CHANGE (skip the first mount). React fires
  // child effects before parent effects, so a fresh detail page's
  // `useBreadcrumbs` commit is preserved on its initial mount.
  useEffect(() => {
    if (prevPathnameRef.current === null) {
      prevPathnameRef.current = pathname;
      return;
    }
    if (prevPathnameRef.current === pathname) {
      return;
    }
    prevPathnameRef.current = pathname;
    setOverrideState(null);
  }, [pathname]);

  const commit = useCallback((next: Crumb[] | null) => {
    setOverrideState((prev) => (sameCrumbArray(prev, next) ? prev : next));
  }, []);

  const value: BreadcrumbSlot = { override, commit };
  return <BreadcrumbContext.Provider value={value}>{children}</BreadcrumbContext.Provider>;
}

function sameCrumbArray(a: Crumb[] | null, b: Crumb[] | null): boolean {
  if (a === b) return true;
  if (a === null || b === null) return false;
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    const x = a[i]!;
    const y = b[i]!;
    if (x.to !== y.to) return false;
    if (x.current !== y.current) return false;
    if (typeof x.label === 'string' && typeof y.label === 'string') {
      if (x.label !== y.label) return false;
    } else {
      if (x.i18nKey !== y.i18nKey) return false;
      if (x.staticLabel !== y.staticLabel) return false;
    }
  }
  return true;
}

/**
 * `useBreadcrumbs(crumbs)` — declare the breadcrumb chain for the
 * current detail page. The argument REPLACES the static chain
 * resolved from `BREADCRUMB_ROUTES`. The effect runs once on mount
 * and re-runs only when the deep-equal comparison detects a
 * content change — inline literal arrays do NOT cause re-fires
 * (no infinite loop).
 */
export function useBreadcrumbs(crumbs: Crumb[]): void {
  const ctx = useContext(BreadcrumbContext);
  // Track the last committed value so we can decide whether to fire
  // the commit. Refs are mutated on every render; the comparison runs
  // inside the effect.
  const lastCommittedRef = useRef<Crumb[] | null>(null);
  useEffect(() => {
    if (ctx === null) return;
    if (sameCrumbArray(lastCommittedRef.current, crumbs)) return;
    lastCommittedRef.current = crumbs;
    ctx.commit(crumbs);
  });
}

/**
 * `useResolvedBreadcrumbs()` — read the final chain. Used by the
 * `<Breadcrumb />` component. Not part of the public surface.
 */
export function useResolvedBreadcrumbs(): ResolvedBreadcrumbs {
  const location = useLocation();
  const pathname = stripTrailingSlash(location.pathname);
  const { selected } = useSucursal();
  const { sucursales } = useSucursalesDirectorio();
  const ctx = useContext(BreadcrumbContext);
  const override = ctx?.override ?? null;

  if (override !== null) {
    return { crumbs: override, entry: null };
  }

  const entry = matchBreadcrumb(pathname);
  if (entry === null) return NULL_RESOLVED;

  // /sucursales/:uuid: resolve the URL branch name as the last segment.
  const urlBranchMatch = /^\/sucursales\/([^/]+)$/.exec(pathname);
  if (urlBranchMatch !== null) {
    const uuid = urlBranchMatch[1]!;
    const found = sucursales.find((s) => s.uuid === uuid);
    const name = found?.nombre ?? found?.prefijo_nombre ?? uuid.slice(0, 8);
    return buildCrumbChain(entry, { to: '/sucursales/' + uuid, label: name, current: true });
  }

  // Branch-scoped entry: assemble the chain as
  //   Inicio → Sucursales → <SucursalActiva> → ...rest → <CurrentSection>
  //
  // Each segment is a real "level" in the navigation hierarchy:
  //   - `Inicio`           → `/`                       (home canónico)
  //   - `Sucursales`       → `/seleccionar-sucursal`   (mismo destino que el sidebar)
  //   - `<SucursalActiva>` → `/dashboard`              (home de la sucursal: donde
  //                                                       aterriza el sidebar tras
  //                                                       que el operador selecciona
  //                                                       una)
  //   - `...rest`          → los segmentos de la tabla (e.g. Reportería → Financiera)
  //   - `<CurrentSection>` → sin link, aria-current="page"
  //
  // Esto se alinea con la jerarquía del sidebar y el comportamiento
  // de la mayoría de los admin UIs: cada crumb es un nivel, y el
  // link del nivel de sucursal es su home, no el picker.
  if (entry.branchScoped === true && selected !== null) {
    const found = sucursales.find((s) => s.uuid === selected);
    const name = found?.nombre ?? found?.prefijo_nombre ?? selected.slice(0, 8);
    const base: Crumb[] = entry.crumbs.map(templateToCrumb);
    if (base.length > 0) {
      base[base.length - 1]!.current = true;
    }
    const sucSec: Crumb = { to: '/seleccionar-sucursal', i18nKey: 'breadcrumb.section.sucursales' };
    const branch: Crumb = { to: '/dashboard', label: name };
    // [Inicio, Sucursales, Branch, ...rest]. `base` ya viene con el
    // último segmento marcado como current.
    const out: Crumb[] = [base[0]!, sucSec, branch, ...base.slice(1)];
    return { crumbs: out, entry };
  }

  return buildCrumbChain(entry);
}

/** Construct a Crumb[] from the entry, optionally overriding the last segment and/or prepending. */
function buildCrumbChain(
  entry: BreadcrumbEntry,
  overrideLast?: Crumb,
  prepend?: Crumb,
): ResolvedBreadcrumbs {
  const base: Crumb[] = entry.crumbs.map(templateToCrumb);
  if (overrideLast !== undefined && base.length > 0) {
    const i = base.length - 1;
    base[i] = { ...base[i]!, ...overrideLast, current: true };
  } else if (base.length > 0) {
    base[base.length - 1]!.current = true;
  }
  const out = prepend !== undefined ? [prepend, ...base] : base;
  return { crumbs: out, entry };
}

function stripTrailingSlash(p: string): string {
  if (p.length > 1 && p.endsWith('/')) return p.slice(0, -1);
  return p;
}
