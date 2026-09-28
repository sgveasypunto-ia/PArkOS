/**
 * `AdminChrome` — the persistent application chrome for authenticated
 * admin routes: translucent top bar, primary nav, identity, logout.
 *
 * NAMING: `main.tsx` already has a local function called `AdminShell`
 * (the bootstrap wrapper that mounts `<App />`). This is a different
 * thing — the visual frame — so it is `AdminChrome` to keep the two
 * apart in stack traces and reviews.
 *
 * CONSUMES THE PR-A DESIGN SYSTEM. The elevation scale, the macOS
 * easing curve and the focus ring existed as tokens but had no consumer,
 * so Tailwind purged them and the utilities were unreachable
 * (verified: `.shadow-elevation-1` was absent from the shipped
 * stylesheet until this component referenced it). Referencing them here
 * is what makes the scale live.
 *
 * ACCESSIBILITY: `<nav aria-label>` landmarks, `NavLink`'s automatic
 * `aria-current="page"` for the active section, and a real `<h1>`-free
 * header (the page owns its heading, so the document keeps exactly one).
 *
 * BRANCH SELECTOR (PR1): the chrome renders a `SucursalSelectorBadge`
 * next to the nav. Clicking it navigates to `/seleccionar-sucursal`,
 * which is the full-page grid where the operator can switch the active
 * branch. We deliberately do NOT render the in-place `BranchSelector`
 * dropdown here — keeping the choice in a single canonical surface
 * (the picker) avoids two competing UI patterns for the same action.
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAdminAuth } from '@parkos/ui-kit/hooks';
import { Building2 } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { visibleSections } from '@/lib/admin-sections';
import { useSucursal } from '@/lib/sucursal-context';

function SucursalSelectorBadge(): JSX.Element | null {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { selected } = useSucursal();
  const { sucursalUuids } = useAdminAuth();

  if (sucursalUuids.length === 0) return null;

  const label = selected
    ? t('chrome.sucursalActive', {
        defaultValue: 'Sucursal activa: {{uuid}}',
        uuid: selected.slice(0, 8),
      })
    : t('chrome.sucursalSelect', { defaultValue: 'Seleccionar sucursal' });

  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      onClick={() => navigate('/seleccionar-sucursal')}
      aria-label={t('chrome.changeBranch', { defaultValue: 'Cambiar sucursal' })}
      data-testid="chrome-sucursal-selector"
      className="gap-2 font-mono text-xs"
    >
      <Building2 className="size-3.5" aria-hidden="true" />
      <span className="hidden sm:inline">{label}</span>
      <span className="sm:hidden" aria-hidden="true">⇄</span>
    </Button>
  );
}

export function AdminChrome() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { rol, permisos, sucursalUuids, logout } = useAdminAuth();
  const [signingOut, setSigningOut] = useState(false);

  const sections = visibleSections(permisos);

  const handleLogout = async (): Promise<void> => {
    setSigningOut(true);
    try {
      // `logoutAdmin` always clears local credentials in its `finally`,
      // so it does not reject today. The catch keeps that guarantee
      // LOCAL to the chrome instead of trusting the hook's internals:
      // a user who asked to log out must always end up on /login, and
      // must never be stranded by an unhandled rejection.
      await logout();
    } catch {
      // Best-effort server-side audit close; the session ends regardless.
    } finally {
      setSigningOut(false);
      navigate('/login', { replace: true });
    }
  };

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <header
        className="surface-translucent sticky top-0 z-40 border-b shadow-elevation-1"
        data-testid="admin-chrome"
      >
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-3 px-4">
          <NavLink
            to="/"
            className="focus-ring flex shrink-0 items-center gap-2 rounded-md text-sm font-semibold tracking-tight"
          >
            <span
              aria-hidden="true"
              className="bg-primary inline-block size-2.5 rounded-full"
            />
            {t('app.name', 'Parkos Admin')}
          </NavLink>

          <nav
            aria-label={t('chrome.navLabel', 'Secciones')}
            className="min-w-0 flex-1 overflow-x-auto"
          >
            <ul className="flex items-center gap-1">
              {sections.map((section) => (
                <li key={section.key}>
                  <NavLink
                    to={section.path}
                    end={section.path === '/'}
                    className={({ isActive }) =>
                      [
                        'focus-ring rounded-md px-2.5 py-1.5 text-sm transition-colors duration-fast ease-macos',
                        isActive
                          ? 'bg-accent text-accent-foreground font-medium'
                          : 'text-muted-foreground hover:bg-accent/60 hover:text-foreground',
                      ].join(' ')
                    }
                  >
                    {t(section.labelKey)}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>

          <div className="flex shrink-0 items-center gap-2">
            <SucursalSelectorBadge />
            {sucursalUuids.length > 0 && (
              <Badge variant="secondary" className="hidden sm:inline-flex">
                {t('chrome.branches', {
                  defaultValue: '{{count}} sucursales',
                  count: sucursalUuids.length,
                })}
              </Badge>
            )}
            {rol && <Badge variant="outline">{rol}</Badge>}
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={handleLogout}
              disabled={signingOut}
              data-testid="admin-logout"
            >
              {signingOut
                ? t('chrome.signingOut', 'Saliendo...')
                : t('chrome.logout', 'Cerrar sesión')}
            </Button>
          </div>
        </div>
      </header>

      <main className="flex-1">
        <Outlet />
      </main>
    </div>
  );
}
