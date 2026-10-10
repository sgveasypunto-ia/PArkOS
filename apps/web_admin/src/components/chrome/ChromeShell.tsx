/**
 * `<ChromeShell />` — the persistent chrome that wraps every authed
 * route except `/login`. Mounted by `App.tsx` in:
 *   - the top-level authed group (covers `/`, `/dashboard`,
 *     `/catalogos`, etc.)
 *   - the `/seleccionar-sucursal` route (the branch picker)
 *
 * Structure:
 *   - `<TopNav />` (identity bar + branch switcher, top of the page)
 *   - `<AppSidebar />` (left nav, 240px wide, hidden below `lg`)
 *   - `<Outlet />` (the route's page content fills the remaining width)
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
import { HUB_CARDS } from '@/pages/GlobalHQ';

export function ChromeShell(): JSX.Element {
  const { permisos } = useAdminAuth();

  return (
    <div className="flex min-h-screen flex-col">
      <TopNav />
      <div className="flex flex-1 min-h-0">
        <AppSidebar items={HUB_CARDS} permisos={permisos} />
        <Outlet />
      </div>
    </div>
  );
}
