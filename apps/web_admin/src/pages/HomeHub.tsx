/**
 * `HomeHub` — landing post-login del administrador.
 *
 * INVARIANTE ARQUITECTÓNICO: esta página se monta FUERA de
 * `<RequireSucursal>`. Por eso no tiene `<AdminChrome />`, no tiene
 * `SucursalSelectorBadge`, no tiene `BranchSelector`. El selector de
 * sucursal aparece SOLO en las rutas gateadas por `<RequireSucursal>`
 * (dashboard, audit, etc.). Agregar `<AdminChrome />` acá expondría el
 * chrome apenas el operador inicia sesión, antes de confirmar la
 * sucursal — una regresión de UX. Pineado por `HomeHub.test.tsx` H1/H2
 * y por `App.test.tsx` "does NOT mount the chrome on /".
 *
 * DEC-LOGIN-07 (revisado): el post-login ya no fuerza
 * `/seleccionar-sucursal`. El admin aterriza acá y la selección de
 * sucursal pasa a ser opt-in vía la card "Sucursales". Las dos cards
 * son las únicas superficies globales — `Catálogos` no requiere
 * sucursal, `Sucursales` es el picker.
 */
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { Building2, FolderTree, Landmark, Users } from 'lucide-react';

import { Card } from '@/components/ui/card';

interface HubCard {
  key: 'sucursales' | 'catalogos' | 'empresa' | 'usuarios';
  path: string;
  icon: typeof Building2;
  titleKey: string;
  descriptionKey: string;
  testId: string;
}

export const HUB_CARDS: readonly HubCard[] = [
  {
    key: 'sucursales',
    path: '/seleccionar-sucursal',
    icon: Building2,
    titleKey: 'homeHub.sucursales.label',
    descriptionKey: 'homeHub.sucursales.description',
    testId: 'home-hub-card-sucursales',
  },
  {
    key: 'catalogos',
    path: '/catalogos',
    icon: FolderTree,
    titleKey: 'homeHub.catalogos.label',
    descriptionKey: 'homeHub.catalogos.description',
    testId: 'home-hub-card-catalogos',
  },
  {
    key: 'empresa',
    path: '/empresa',
    icon: Landmark,
    titleKey: 'homeHub.empresa.label',
    descriptionKey: 'homeHub.empresa.description',
    testId: 'home-hub-card-empresa',
  },
  {
    key: 'usuarios',
    path: '/usuarios',
    icon: Users,
    titleKey: 'homeHub.usuarios.label',
    descriptionKey: 'homeHub.usuarios.description',
    testId: 'home-hub-card-usuarios',
  },
] as const;

export default function HomeHub(): JSX.Element {
  const { t } = useTranslation();

  return (
    <div className="mx-auto max-w-6xl px-4 py-10" data-testid="home-hub">
      <header className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight">
          {t('homeHub.title', 'Todo el parqueo, en un solo lugar')}
        </h1>
        <p className="text-muted-foreground mt-2 text-sm">
          {t('homeHub.subtitle', 'Elegí una sección para empezar.')}
        </p>
      </header>

      <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {HUB_CARDS.map((card) => {
          const Icon = card.icon;
          return (
            <li key={card.key}>
              <Link
                to={card.path}
                data-testid={card.testId}
                aria-label={t(card.titleKey)}
                className="focus-ring block rounded-xl transition-shadow duration-base ease-macos hover:shadow-elevation-2"
              >
                <Card className="h-full p-5">
                  <div className="flex items-start gap-3">
                    <span
                      aria-hidden="true"
                      className="bg-primary/10 text-primary inline-flex size-10 shrink-0 items-center justify-center rounded-lg"
                    >
                      <Icon className="size-5" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <h2 className="text-base font-semibold tracking-tight">
                        {t(card.titleKey)}
                      </h2>
                      <p className="text-muted-foreground mt-1.5 text-sm">
                        {t(card.descriptionKey)}
                      </p>
                    </div>
                  </div>
                  <span className="text-primary mt-4 inline-block text-sm font-medium">
                    {t('homeHub.open', 'Abrir')}
                    <span aria-hidden="true"> →</span>
                  </span>
                </Card>
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
