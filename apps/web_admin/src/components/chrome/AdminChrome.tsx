/**
 * `AdminChrome` — layout wrapper for branch-scoped routes.
 *
 * The header (brand, nav, branch selector, logout) now lives in
 * `<TopNav showBranchNav />`. This component only provides the
 * `<main>` wrapper for the `<Outlet />`.
 *
 * NAMING: `main.tsx` already has a local function called `AdminShell`
 * (the bootstrap wrapper that mounts `<App />`). This is a different
 * thing — the visual frame — so it is `AdminChrome` to keep the two
 * apart in stack traces and reviews.
 */
import { Outlet } from 'react-router-dom';

export function AdminChrome(): JSX.Element {
  return (
    <main className="flex-1">
      <Outlet />
    </main>
  );
}
