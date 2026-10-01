/**
 * `UsuariosDetalleNavigation.test.tsx` — reachability regression test.
 *
 * The bug this pins: the HU-F16 detail screen (permisos / update / reset
 * / bitácora / sesiones) was fully implemented and unit-tested, yet no
 * link pointed at it. `App.tsx` mounted `/usuarios/:uuid`, but
 * `AdminUsuarioTable` rendered no `<Link>` and no `useNavigate`, so the
 * only way in was hand-typing a uuid. Two docblocks also claimed the
 * backend had no PUT endpoint, which is false and actively hid the
 * feature from anyone reading the code.
 *
 * The component tests for `PermisosTree` / `UsuarioForm` could not catch
 * this: they render the component directly with the route injected by
 * hand, so "the component works" and "a human can reach it" stayed
 * unrelated claims.
 *
 * The mock is on `parkosFetch` **by URL**, not on the SWR hooks.
 * Mocking the hook would let this file pass even if the API path or the
 * Zod schema were broken — which is precisely the false positive this
 * test exists to eliminate. Routing by URL also exercises the whole
 * chain: SWR -> hook -> parkosFetch -> Zod parse -> render.
 */
import { describe, expect, it, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { SWRConfig } from 'swr';
import { SucursalProvider } from '@/lib/sucursal-context';

import App from './App';

vi.mock('@parkos/ui-kit/hooks', () => ({
  useAdminAuth: () => ({
    user: {
      uuid: '00000000-0000-0000-0000-0000000000ad',
      email: 'admin@parkos.local',
    },
    rol: 'admin',
    sucursalUuids: ['2049f2cd-b2a8-4e45-9d19-31fa87eb67c6'],
    permisos: ['admin_usuarios', 'audit_read'],
    isAuthenticated: true,
    isLoading: false,
    error: undefined,
    refresh: async () => undefined,
    logout: async () => undefined,
  }),
}));

// Shared fixtures. Declared via `vi.hoisted` because `vi.mock` factories
// are hoisted above module-level `const`s: referencing USER_UUID inside
// the factory would hit the temporal dead zone.
const { USER_UUID, USUARIO, calls } = vi.hoisted(() => {
  const uuid = '11111111-1111-1111-1111-111111111111';
  return {
    USER_UUID: uuid,
    calls: [] as string[],
    USUARIO: {
      uuid,
      nombre: 'Ana',
      apellido: 'Ruiz',
      cedula: '123',
      email: 'ana@parkos.local',
      rol: 'admin',
      vigente_desde: '2026-01-01T00:00:00Z',
      vigente_hasta: null,
      estado: 'activo',
      created_at: '2026-01-01T00:00:00Z',
      created_by: null,
      sync_status: null,
      sucursales: [],
    },
  };
});

// The app has TWO transports for this same resource:
//   - the list  (`features/admin/api/adminUsuariosApi.ts`) uses
//     `parkosFetchRaw` imported straight from `@parkos/ui-kit/fetch`
//     and expects a `Response` back;
//   - the detail (`features/usuarios/api/usuariosApi.ts`) uses
//     `parkosFetch` re-exported through `@/lib/fetch` and expects the
//     decoded body.
// Mocking `@/lib/fetch` alone silently left the LIST hitting the real
// network -- which is why the first run of this file failed with
// "No se pudo cargar el listado" rather than a link problem. Mock the
// package both derive from so the whole navigation path is offline.
//
// List and detail are DIFFERENT urls: `/admin/usuarios/{uuid}` does not
// end with `/admin/usuarios`, so they are matched separately.
vi.mock('@parkos/ui-kit/fetch', () => {
  const LIST = '/api/v1/admin/usuarios';
  const DETAIL = `${LIST}/${USER_UUID}`;

  const bodyFor = (url: string): unknown => {
    calls.push(url);
    if (url === LIST) return { items: [USUARIO], next_cursor: null };
    if (url === DETAIL) return USUARIO;
    // permisos / sucursales / sesiones / login-historico / sucursales dir
    return [];
  };

  return {
    parkosFetch: (url: string) => Promise.resolve(bodyFor(url)),
    parkosFetchRaw: (url: string) =>
      Promise.resolve(
        new Response(JSON.stringify(bodyFor(url)), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    ParkosHttpError: class ParkosHttpError extends Error {},
  };
});

const ALLOWED_UUID = '2049f2cd-b2a8-4e45-9d19-31fa87eb67c6';

function Providers({ children }: { children: React.ReactNode }): JSX.Element {
  return (
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      <SucursalProvider>{children}</SucursalProvider>
    </SWRConfig>
  );
}

function renderEnUsuarios(): void {
  render(
    <Providers>
      <MemoryRouter initialEntries={['/usuarios']}>
        <App />
      </MemoryRouter>
    </Providers>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  calls.length = 0;
  window.localStorage.setItem('parkos.lastSelectedSucursal', ALLOWED_UUID);
});

describe('Alcance del detalle de usuario', () => {
  it('expone un link navegable al detalle desde la fila', async () => {
    renderEnUsuarios();

    const link = await screen.findByTestId(
      `admin-row-${USER_UUID}-detail-link`,
    );
    expect(link).toHaveAttribute('href', `/usuarios/${USER_UUID}`);
  });

  it('expone el boton Detalle con su i18n', async () => {
    renderEnUsuarios();

    const boton = await screen.findByTestId(`admin-row-${USER_UUID}-detalle`);
    expect(boton).toHaveTextContent('Detalle');
    expect(boton).toHaveAttribute('href', `/usuarios/${USER_UUID}`);
  });

  it('navega al detalle y monta los cinco tabs al clickear el link', async () => {
    renderEnUsuarios();

    await userEvent.click(
      await screen.findByTestId(`admin-row-${USER_UUID}-detail-link`),
    );

    // Reaching the detail must actually fire the per-user fetch — proof
    // the screen is live and not just painted.
    await waitFor(() => {
      expect(calls).toContain(`/api/v1/admin/usuarios/${USER_UUID}`);
    });

    for (const tab of ['Datos', 'Permisos', 'Sucursales', 'Bitácora', 'Sesiones']) {
      expect(await screen.findByRole('tab', { name: tab })).toBeInTheDocument();
    }
  });

  it('navega al detalle al clickear el boton Detalle', async () => {
    renderEnUsuarios();

    await userEvent.click(await screen.findByTestId(`admin-row-${USER_UUID}-detalle`));

    await waitFor(() => {
      expect(calls).toContain(`/api/v1/admin/usuarios/${USER_UUID}`);
    });
    expect(await screen.findByRole('tab', { name: 'Permisos' })).toBeInTheDocument();
  });

  it('deja accesible el reset de contrasena desde el detalle', async () => {
    renderEnUsuarios();

    await userEvent.click(
      await screen.findByTestId(`admin-row-${USER_UUID}-detail-link`),
    );

    // This is the whole point of the entry point: the reset control must
    // be one click past a reachable detail, not buried behind a uuid.
    expect(await screen.findByTestId('reset-password-btn')).toBeInTheDocument();
  });
});
