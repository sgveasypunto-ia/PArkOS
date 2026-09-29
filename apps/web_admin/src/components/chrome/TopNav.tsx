/**
 * `<TopNav />` — top bar con la identidad del admin (email, rol, logout)
 * en TODAS las rutas autenticadas de `web_admin` excepto `/login`.
 *
 * NO monta la nav de secciones ni el badge de sucursal: esa responsabilidad
 * sigue en `<AdminChrome />` y solo aparece en las rutas branch-scoped.
 * Las dos barras viven una arriba de la otra en esas rutas y comparten
 * estilo (`surface-translucent` + `border-b` + `shadow-elevation-1`)
 * para que se lean como una sola pieza de dos filas.
 *
 * RESPONSABILIDADES:
 *   - Brand "Parkos Admin" como link a `/`.
 *   - Avatar del usuario con la inicial del email (o dos iniciales si
 *     `useAdminAuth` ya trae `nombre`/`apellido`; hoy vienen `null`).
 *   - Email del usuario, truncado en pantallas chicas.
 *   - Dropdown (primitivo propio) con:
 *       * Cabecera: avatar + email + rol.
 *       * "Mi perfil" -> navega a `/perfil`.
 *       * "Configuración" -> disabled con tooltip "Próximamente".
 *       * "Cerrar sesión" -> `logout()` + `navigate('/login')`, con
 *         estado `signingOut` para evitar doble-click.
 *
 * POR QUE NO SE MONTA EN /login:
 *   El `Login` es la unica ruta que no esta envuelta en
 *   `<RequireAdmin>`, asi que su render no toca el store. Ademas,
 *   `<TopNav />` lee `useAdminAuth().user`, que en `/login` o es null
 *   (no hay token) o esta transicionando (post-login). El propio
 *   `App.tsx` deja `/login` fuera del wrap con `<TopNav />`, asi que
 *   ni siquiera se monta.
 *
 * INVARIANTE:
 *   - `user.email` puede ser `null` segun `AdminMeResponse.email:
 *     string | null`. Cuando lo es, mostramos el UUID acortado como
 *     fallback para que el top bar nunca quede con el avatar solo.
 *   - `logout()` desde `useAdminAuth` ya hace `clear()` local en
 *     `finally`; lo envolvemos igual que `AdminChrome::handleLogout`
 *     para que la navegacion a `/login` sea siempre local, jamas
 *     delegada al backend.
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router-dom';
import { useAdminAuth } from '@parkos/ui-kit/hooks';
import { LogOut, Settings, UserCircle2 } from 'lucide-react';

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

function avatarLabel(email: string | null, uuid: string): string {
  if (email && email.length > 0) {
    const at = email.indexOf('@');
    const local = (at === -1 ? email : email.slice(0, at)).trim();
    if (local.length > 0) return local[0]!.toUpperCase();
  }
  return uuid.slice(0, 1).toUpperCase();
}

function displayEmail(email: string | null, uuid: string): string {
  if (email && email.length > 0) return email;
  return `${uuid.slice(0, 8)}…`;
}

export function TopNav(): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { user, rol, logout } = useAdminAuth();
  const [signingOut, setSigningOut] = useState(false);

  const email = user?.email ?? null;
  const uuid = user?.uuid ?? '';
  const initial = avatarLabel(email, uuid);
  const displayed = displayEmail(email, uuid);

  const handleLogout = async (): Promise<void> => {
    setSigningOut(true);
    try {
      await logout();
    } catch {
      // Best-effort: `logoutAdmin` ya limpia local en `finally`, asi que
      // un rechazo solo significa que el audit close server-side no
      // llego. La sesion igual termina.
    } finally {
      setSigningOut(false);
      navigate('/login', { replace: true });
    }
  };

  return (
    <header data-testid="topnav">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-3 px-4">
        <Link
          to="/"
          className="focus-ring flex shrink-0 items-center gap-2 rounded-md text-sm font-semibold tracking-tight"
          data-testid="topnav-brand"
          aria-label={t('topnav.brand', 'Parkos Admin')}
        >
          <span
            aria-hidden="true"
            className="bg-primary inline-block size-2.5 rounded-full"
          />
          {t('app.name', 'Parkos Admin')}
        </Link>

        <div className="min-w-0 flex-1" aria-hidden="true" />

        <DropdownMenu>
          <DropdownMenuTrigger
            className="focus-ring flex shrink-0 items-center gap-2 rounded-full p-1 pr-3 text-sm hover:bg-accent/60"
            data-testid="topnav-user-menu"
            aria-label={t('topnav.userMenu', 'Menú de usuario')}
          >
            <span
              aria-hidden="true"
              data-testid="topnav-avatar"
              className="bg-primary/10 text-primary inline-flex size-8 items-center justify-center rounded-full text-sm font-semibold"
            >
              {initial}
            </span>
            <span
              data-testid="topnav-email"
              className="hidden max-w-[180px] truncate font-medium md:inline"
            >
              {displayed}
            </span>
          </DropdownMenuTrigger>

          <DropdownMenuContent align="end" className="min-w-[16rem]">
            <DropdownMenuLabel className="flex flex-col gap-0.5">
              <span
                data-testid="topnav-dropdown-email"
                className="truncate font-medium"
              >
                {displayed}
              </span>
              {rol && (
                <span className="text-muted-foreground text-xs">{rol}</span>
              )}
            </DropdownMenuLabel>

            <DropdownMenuSeparator />

            <DropdownMenuItem
              onClick={() => navigate('/perfil')}
              data-testid="topnav-profile"
            >
              <UserCircle2 className="size-4" aria-hidden="true" />
              {t('topnav.profile', 'Mi perfil')}
            </DropdownMenuItem>

            <DropdownMenuItem
              disabled
              title={t('topnav.settingsSoon', 'Próximamente')}
              data-testid="topnav-settings"
            >
              <Settings className="size-4" aria-hidden="true" />
              {t('topnav.settings', 'Configuración')}
            </DropdownMenuItem>

            <DropdownMenuSeparator />

            <DropdownMenuItem
              onClick={() => void handleLogout()}
              disabled={signingOut}
              destructive
              closeOnSelect={false}
              data-testid="topnav-logout"
            >
              <LogOut className="size-4" aria-hidden="true" />
              {signingOut
                ? t('topnav.signingOut', 'Saliendo…')
                : t('topnav.logout', 'Cerrar sesión')}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
