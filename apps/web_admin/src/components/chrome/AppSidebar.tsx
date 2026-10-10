/**
 * `<AppSidebar />` — left-side persistent nav, present on every authed
 * route except `/login`. Replaces the in-page "accesos rápidos" rail
 * that used to live at the bottom of `<GlobalHQ />` (the rail had a
 * 725px height on 1080p and the user reported the access links "se
 * perdían" below the fold).
 *
 * Layout: 240px wide, sticky to the top of the viewport, hidden below
 * `lg` (mobile navigation is a separate follow-up -- this PR is
 * desktop-first). The page content lives to the right of the sidebar
 * in a flex row, mounted by the App layout shell.
 *
 * Active state: each item is a `<NavLink>` so react-router injects
 * `aria-current="page"` when the path matches the current URL. The
 * active row gets `bg-accent` + `font-semibold` (stronger than hover
 * so the operator always knows where they are).
 *
 * Permission filtering: items declare an optional `permission`. Items
 * with `null` are visible to any admin; items with a string are
 * filtered against the actor's `permisos[]` from `useAdminAuth()`. The
 * 8 items come from `HUB_CARDS` in `pages/GlobalHQ.tsx` (re-exported
 * from there for the test to keep the data-driven contract from
 * `HomeHub.test.tsx` days).
 *
 * INVARIANTE: el branch selector (testid `chrome-sucursal-selector`)
 * sigue viviendo en `<TopNav>` y SOLO se monta cuando `selected !==
 * null`. El sidebar es puramente navegacion: no toca `useSucursal()`,
 * no asume branch. Por eso puede (y debe) montarse en `/` aunque esa
 * ruta este fuera de `<RequireSucursal>`.
 */
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { NavLink } from 'react-router-dom';
import { ChevronRight, type LucideIcon } from 'lucide-react';

export interface SidebarItem {
  key: string;
  path: string;
  icon: LucideIcon;
  labelKey: string;
  /** Permission gate, mirrors the convention in `lib/admin-sections.ts`:
   *  `null` = any admin; string = required permission in `permisos[]`. */
  permission: string | null;
  /** Test id, kept stable across the rail/sidebar migration so the
   *  smoke tests in `App.test.tsx` (HomeHub era) keep working. */
  testId: string;
}

export interface AppSidebarProps {
  items: readonly SidebarItem[];
  /** Actor's granted permissions from `useAdminAuth().permisos`. */
  permisos: readonly string[];
}

function isVisible(item: SidebarItem, granted: ReadonlySet<string>): boolean {
  if (item.permission === null) return true;
  return granted.has(item.permission);
}

export function AppSidebar({ items, permisos }: AppSidebarProps): JSX.Element {
  const { t } = useTranslation();
  const visible = useMemo(() => {
    const granted = new Set(permisos);
    return items.filter((it) => isVisible(it, granted));
  }, [items, permisos]);

  return (
    <aside
      className="hidden w-60 shrink-0 border-r border-border/40 bg-card/30 lg:block"
      aria-label={t('sidebar.title', 'Navegación principal')}
      data-testid="app-sidebar"
    >
      <nav className="sticky top-0 p-3">
        <ul className="flex flex-col gap-0.5">
          {visible.map((item) => {
            const Icon = item.icon;
            return (
              <li key={item.key}>
                <NavLink
                  to={item.path}
                  end={item.path === '/'}
                  data-testid={item.testId}
                  aria-label={t(item.labelKey)}
                  className={({ isActive }) =>
                    [
                      'group',
                      'focus-ring',
                      'flex',
                      'items-center',
                      'gap-3',
                      'rounded-md',
                      'px-2',
                      'py-2',
                      'text-sm',
                      'font-medium',
                      'transition-colors',
                      'duration-base',
                      'ease-macos',
                      isActive
                        ? 'bg-accent text-accent-foreground font-semibold'
                        : 'text-foreground hover:bg-accent/60 hover:text-accent-foreground',
                    ].join(' ')
                  }
                >
                  <Icon
                    aria-hidden={true}
                    className="text-muted-foreground group-hover:text-foreground size-4 shrink-0"
                  />
                  <span className="min-w-0 flex-1 truncate">
                    {t(item.labelKey)}
                  </span>
                  <ChevronRight
                    aria-hidden="true"
                    className="text-muted-foreground group-hover:text-foreground size-4 shrink-0 transition-transform duration-base ease-macos group-hover:translate-x-0.5"
                  />
                </NavLink>
              </li>
            );
          })}
        </ul>
      </nav>
    </aside>
  );
}
