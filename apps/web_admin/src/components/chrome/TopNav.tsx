/**
 * `<TopNav />` — top bar con la identidad del admin (email, rol, logout)
 * en TODAS las rutas autenticadas de `web_admin` excepto `/login`.
 *
 * RESPONSABILIDADES:
 *   - Brand "EasyPunto" (logo real, swap light/dark) como link a `/`.
 *   - Operador + sucursal visibles (md+) con la misma forma visual que
 *     `apps/electron-sucursal/src/features/caja/pages/Dashboard.tsx`.
 *   - Avatar del usuario con la inicial del email.
 *   - Email del usuario, truncado en pantallas chicas.
 *   - Dropdown (Radix via shadcn) con:
 *       * Cabecera: avatar + email + rol.
 *       * "Mi perfil" -> navega a `/perfil`.
 *       * "Configuración" -> disabled con tooltip "Próximamente".
 *       * "Cerrar sesión" -> `logout()` + `navigate('/login')`.
 *   - Branch-switch shortcut (admin only) -> `/seleccionar-sucursal`.
 *   - Theme toggle (Radix via shadcn).
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
 *   - `useAdminAuth` NUNCA expone `nombre`/`apellido` del usuario
 *     (siempre `null`, ver `apps/ui-kit/src/hooks/useAdminAuth.ts`
 *     linea 119) y el `useSucursal()` del admin solo guarda el UUID
 *     seleccionado, no la ficha completa de la sucursal. Por eso el
 *     bloque operador/sucursal cae a fallbacks (`email-prefix` y
 *     `uuid.slice(0, 8)`) en vez de mostrar el nombre real. La
 *     estructura visual sigue siendo 1:1 con el Dashboard de la
 *     sucursal — el shell, el divider, el `flex-1` que absorbe el
 *     espacio vacio, y el `ml-auto` que ancla el cluster derecho.
 *   - `logout()` desde `useAdminAuth` ya hace `clear()` local en
 *     `finally`; lo envolvemos para que la navegacion a `/login` sea
 *     siempre local, jamas delegada al backend.
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router-dom';
import { useAdminAuth } from '@parkos/ui-kit/hooks';
import { Building2, LogOut, Settings, UserCircle2 } from 'lucide-react';

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useSucursal } from '@/lib/sucursal-context';
import { ThemeToggle } from '@/components/chrome/ThemeToggle';

import logoLight from '@/assets/brand/logos/logo-horizontal-light.svg';
import logoDark from '@/assets/brand/logos/logo-horizontal-dark--REQUIERE-VECTOR.png';

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
  const { selected } = useSucursal();
  const [signingOut, setSigningOut] = useState(false);

  const email = user?.email ?? null;
  const uuid = user?.uuid ?? '';
  const initial = avatarLabel(email, uuid);
  const displayed = displayEmail(email, uuid);

  // Operador — la API admin no expone `nombre`/`apellido` del actor
  // (ver docblock arriba), asi que el email-prefix es el mejor
  // fallback disponible. Si no hay email tampoco, "Administrador".
  const emailLocal =
    email && email.length > 0
      ? (email.split('@')[0] ?? '').trim()
      : '';
  const operadorLabel =
    emailLocal !== ''
      ? emailLocal
      : t('common:administrador', { defaultValue: 'Administrador' });

  // Sucursal — `useSucursal()` solo guarda el UUID seleccionado, no
  // la ficha con `prefijo_nombre`/`nombre`. Replicamos la forma del
  // Dashboard (`<uuid corto>…` cuando hay algo, i18n fallback cuando
  // no) sin inventar un fetch que exceda el scope de este cambio.
  const sucursalLabel =
    selected && selected.length > 0
      ? `${selected.slice(0, 8)}…`
      : t('common:sucursal', { defaultValue: 'Sucursal' });

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
    <header
      data-testid="topnav"
      className="flex min-w-0 flex-wrap items-center gap-2 border-b border-border/40 bg-card/80 px-4 py-2.5 backdrop-blur-md shadow-apple-sm md:gap-3 md:px-5 xl:px-6"
    >
      {/* Brand — EasyPunto logo (light/dark swap via `.dark` en
          `<html>`, igual que el Dashboard de la sucursal). El
          `<span className="sr-only">` mantiene un nombre accesible
          razonable para screen readers y para la traduccion
          `topnav.brand` que ya esta en uso. */}
      <Link
        to="/"
        data-testid="topnav-brand"
        className="focus-ring flex shrink-0 items-center gap-2 rounded-md"
        aria-label={t('topnav.brand', 'Parkos Admin')}
      >
        <img
          src={logoLight}
          alt=""
          aria-hidden="true"
          className="h-9 w-auto shrink-0 dark:hidden"
        />
        <img
          src={logoDark}
          alt=""
          aria-hidden="true"
          className="hidden h-9 w-auto shrink-0 dark:block"
        />
        <span className="sr-only">{t('topnav.brand', 'Parkos Admin')}</span>
      </Link>

      {/* Divisor vertical logo ↔ bloque operador/sucursal. Mismo
          patron que Dashboard.tsx:283. Solo md+ porque el bloque
          tampoco se renderiza en mobile. */}
      <div className="hidden h-8 w-px shrink-0 bg-border mx-5 md:block" />

      {/* Operador + sucursal — `hidden md:flex` para no inflar el
          header en mobile/phablet. `flex-1` absorbe el espacio vacio
          entre el divisor y el cluster derecho (que vive en `ml-auto`
          mas abajo), igual que Dashboard.tsx:307-312. */}
      <div className="hidden min-w-0 flex-1 flex-col leading-tight md:flex">
        <strong
          className="truncate text-base"
          data-testid="topnav-operador-name"
        >
          {operadorLabel}
        </strong>
        <span
          className="truncate text-sm text-muted-foreground"
          data-testid="topnav-operador-sucursal"
        >
          {sucursalLabel}
        </span>
      </div>

      {/* Cluster derecho — `ml-auto` lo ancla al borde derecho del
          header; el `flex-1` del bloque operador-sucursal se come
          el espacio sobrante. `flex-wrap` + `justify-end` son la
          red de seguridad si en 320px algo no cabe junto. Mismo
          shell que Dashboard.tsx:330-356. */}
      <div className="ml-auto flex flex-wrap items-center justify-end gap-2">
        {/*
          Branch-switch shortcut. Only renders once the operator has
          actually picked a branch — before that the picker in
          HomeHub is the entry point, and showing the shortcut would
          be circular (the button just takes you to the same picker).
          After the first branch selection this button lets the
          operator swap branches without first going back to HomeHub.
        */}
        {selected !== null && (
          <button
            type="button"
            onClick={() => navigate('/seleccionar-sucursal')}
            data-testid="chrome-sucursal-selector"
            className="focus-ring inline-flex shrink-0 items-center gap-2 rounded-md border border-input bg-background px-3 py-1.5 text-sm font-medium hover:bg-accent/60"
            aria-label={t('topnav.switchBranch', 'Cambiar sucursal')}
          >
            <Building2 className="size-4" aria-hidden="true" />
            <span className="hidden md:inline">
              {t('topnav.switchBranch', 'Cambiar sucursal')}
            </span>
          </button>
        )}

        <ThemeToggle />

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
