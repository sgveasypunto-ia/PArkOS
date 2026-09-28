/**
 * `Home` — the admin's landing page and navigation hub.
 *
 * This is the `/` route. `/dashboard` keeps its own identity: it is the
 * per-branch operational panel, not the app's front door.
 *
 * Shows one card per section in `ADMIN_SECTIONS` that the actor can
 * actually reach. No placeholder cards, no links to routes that do not
 * exist yet — a hub that advertises unfinished surfaces is worse than a
 * hub that shows four real ones. Cupos, tarifas and reports are absent
 * from the catalog until their routes exist.
 *
 * LOADING IS DELIBERATELY NOT AN EMPTY GRID. `permisos` is empty until
 * `/admin/me` resolves, and the only gated section (Auditoría) is
 * invisible in that window. Rendering "nothing" during the fetch is the
 * exact failure this page exists to prevent, so the pending state is an
 * explicit `role="status"` region instead.
 */
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { useAdminAuth } from '@parkos/ui-kit/hooks';

import { Card } from '@/components/ui/card';
import { visibleSections } from '@/lib/admin-sections';

export default function Home() {
  const { t } = useTranslation();
  const { permisos, isLoading, user, sucursalUuids } = useAdminAuth();

  const sections = visibleSections(permisos);
  const displayName =
    [user?.nombre, user?.apellido].filter(Boolean).join(' ') || user?.email || '';

  return (
    <div className="mx-auto max-w-6xl px-4 py-10" data-testid="page-home">
      <header className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight">
          {t('home.title', 'Todo el parqueo, en un solo lugar')}
        </h1>
        <p className="text-muted-foreground mt-2 text-sm">
          {displayName
            ? t('home.subtitleNamed', { defaultValue: 'Sesión de {{name}}.', name: displayName })
            : t('home.subtitle', 'Elegí una sección para empezar.')}
        </p>
      </header>

      {isLoading ? (
        <p
          role="status"
          aria-live="polite"
          className="text-muted-foreground text-sm"
          data-testid="home-loading"
        >
          {t('home.loading', 'Cargando tus secciones...')}
        </p>
      ) : sections.length === 0 ? (
        <p className="text-muted-foreground text-sm" data-testid="home-empty">
          {t('home.empty', 'No tenés secciones disponibles con tu rol.')}
        </p>
      ) : (
        <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {sections.map((section) => (
            <li key={section.key}>
              <Link
                to={section.path}
                data-testid={`home-card-${section.key}`}
                className="focus-ring block rounded-xl transition-shadow duration-base ease-macos hover:shadow-elevation-2"
              >
                <Card className="h-full p-5">
                  <div className="flex items-start justify-between gap-3">
                    <h2 className="text-base font-semibold tracking-tight">
                      {t(section.labelKey)}
                    </h2>
                    {section.permission && (
                      <span className="text-muted-foreground shrink-0 text-[11px] uppercase tracking-wide">
                        {section.permission}
                      </span>
                    )}
                  </div>
                  <p className="text-muted-foreground mt-1.5 text-sm">
                    {t(section.descriptionKey)}
                  </p>
                  <span className="text-primary mt-4 inline-block text-sm font-medium">
                    {t('home.open', 'Abrir')}
                    <span aria-hidden="true"> →</span>
                  </span>
                </Card>
              </Link>
            </li>
          ))}
        </ul>
      )}

      {sucursalUuids.length > 0 && (
        <p className="text-muted-foreground mt-8 text-xs" data-testid="home-scope">
          {t('home.scope', {
            defaultValue:
              'Alcance: {{count}} sucursal(es) autorizada(s). Las métricas y el log de auditoría se filtran por la sucursal seleccionada.',
            count: sucursalUuids.length,
          })}
        </p>
      )}
    </div>
  );
}
