/**
 * `<ChromeShell />` — the persistent chrome that wraps every authed
 * route except `/login`. Mounted by `App.tsx` in:
 *   - the top-level authed group (covers `/`, `/dashboard`,
 *     `/catalogos`, etc.)
 *   - the `/seleccionar-sucursal` route (the branch picker)
 *
 * Structure:
 *   - `<TopNav />` (identity bar + branch switcher, top of the page)
 *   - `<Breadcrumb />` (navigation trail, just below the TopNav)
 *   - `<AppSidebar />` (left nav, 240px wide, hidden below `lg`)
 *   - `<Outlet />` (the route's page content fills the remaining width)
 *
 * The `<BreadcrumbsProvider />` lives here so detail pages (anywhere
 * under the chrome shell) can call `useBreadcrumbs([...])` to override
 * the static chain with the resource's real name. Same dual-call
 * pattern as `useAdminAuth` -- harmless.
 *
 * Calls `useAdminAuth()` to feed `permisos` into `<AppSidebar />` for
 * permission-aware filtering of the 8 nav items. The same hook is
 * also called at the `App` root — double-call is fine (SWR dedup +
 * Zustand-backed auth state, both cheap). Putting it here keeps
 * `<ChromeShell />` self-contained so any future caller (a modal
 * that wants the full chrome, a preview, a storybook story) can
 * drop it in without threading props.
 */
import { Outlet } from 'react-router-dom';
import { useAdminAuth } from '@parkos/ui-kit/hooks';

import { TopNav } from './TopNav';
import { AppSidebar } from './AppSidebar';
import { Breadcrumb } from './Breadcrumb';
import { HUB_CARDS } from '@/pages/GlobalHQ';
import { BreadcrumbsProvider } from '@/lib/useBreadcrumbs';

export function ChromeShell(): JSX.Element {
  const { permisos } = useAdminAuth();

  return (
    <BreadcrumbsProvider>
      <div className="flex min-h-screen flex-col">
        <TopNav />
        <Breadcrumb />
        <div className="flex flex-1 min-h-0">
          <AppSidebar items={HUB_CARDS} permisos={permisos} />
          {/*
            F17.x/ChromeShell layout follow-up: the page Outlet is a flex
            child of this row but had no `flex-1 min-w-0`, so its width
            followed the *content's* intrinsic min-width instead of the
            remaining row width (1395 − 240 sidebar = 1155). The
            /reporteria and /reporteria/financiera pages exposed the
            bug because their `<main>` does not carry `flex flex-1`
            (the long "Todas las sucursales" subtitle pushed main wider
            than the short per-branch one — 118 / 305 px of dead space
            on the right). Wrapping the Outlet in `flex-1 min-w-0` (a
            BLOCK wrapper, NOT a flex container — the inner `<main>` is
            a block child and would otherwise become a flex item with
            content-driven width) makes the page fill the row by
            default; the rare page that needs a fixed width can still
            opt out by setting its own `max-w-*` on `<main>`. `min-w-0`
            is required so the wrapper can shrink below its content's
            intrinsic min-width (the table's `overflow-auto` already
            handles the per-cell overflow inside the page).
          */}
          <div className="flex-1 min-w-0">
            <Outlet />
          </div>
        </div>
      </div>
    </BreadcrumbsProvider>
  );
}
