/**
 * `UsuariosList.test.tsx` — HU-F16.2 filter tests (rol/sucursal/estado)
 * + the create-wizard swap-in smoke test.
 *
 * The filtering rule itself is exercised directly against the exported
 * pure `filterUsuarios` helper (fast, no rendering/mocking needed). A
 * lighter page-level smoke test then renders `<UsuariosList />` with the
 * fetch layer mocked (same seam as `AdminUsuarioTable.test.tsx`) to
 * confirm the filter controls are wired to the table.
 *
 * HU-X.8 follow-up: the branch filter was pulled out of the local
 * `UsuariosFiltros` and now follows the global `SucursalContext`
 * (`useSucursal().selected`). The pure-helper signature changed to
 * `filterUsuarios(rows, filtros, sucursalUuid)` and the page-level
 * tests wrap the render in a `SucursalProvider` so the new
 * `useSucursal()` call inside `UsuariosList` resolves.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createElement, type ReactNode } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SWRConfig } from 'swr';
import { MemoryRouter } from 'react-router-dom';

import { SucursalProvider } from '@/lib/sucursal-context';

vi.mock('@parkos/ui-kit/fetch', () => ({
  parkosFetchRaw: vi.fn(),
  parkosFetch: vi.fn(),
}));

import { parkosFetchRaw } from '@parkos/ui-kit/fetch';

import UsuariosList from './UsuariosList';
import { filterUsuarios } from './usuariosListFilters';
import type { AdminUsuarioRead } from '../api/adminUsuarioSchema';

const mockedRaw = vi.mocked(parkosFetchRaw);

const SUC_NORTE = 'aaaa1111-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
const SUC_SUR = 'bbbb2222-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
const UUID_ADMIN = '11111111-1111-4111-8111-111111111111';
const UUID_OPERADOR = '22222222-2222-4222-8222-222222222222';

function makeRow(overrides: Partial<AdminUsuarioRead> = {}): AdminUsuarioRead {
  return {
    uuid: '83ef5d9f-dd65-47e3-9b13-50deed0f03d3',
    email: 'user@parkos.local',
    nombre: null,
    apellido: null,
    cedula: null,
    rol: 'operador',
    vigente_desde: '2026-01-01T00:00:00Z',
    vigente_hasta: null,
    estado: 'activo',
    created_at: '2026-01-01T00:00:00Z',
    created_by: null,
    sync_status: null,
    sucursales: [],
    ...overrides,
  };
}

describe('filterUsuarios (pure filtering logic)', () => {
  const admin1 = makeRow({
    uuid: '1',
    rol: 'admin',
    estado: 'activo',
    sucursales: [{ uuid_sucursal: SUC_NORTE, nombre: 'Norte', prefijo_nombre: 'NOR', vigente_desde: '2026-01-01' }],
  });
  const operador1 = makeRow({
    uuid: '2',
    rol: 'operador',
    estado: 'activo',
    sucursales: [{ uuid_sucursal: SUC_SUR, nombre: 'Sur', prefijo_nombre: 'SUR', vigente_desde: '2026-01-01' }],
  });
  const operadorInactivo = makeRow({ uuid: '3', rol: 'operador', estado: 'inactivo', sucursales: [] });
  const rows = [admin1, operador1, operadorInactivo];

  it('returns every row when every filter is "" (no filter) and no branch is selected', () => {
    expect(filterUsuarios(rows, { rol: '', estado: '' }, null)).toEqual(rows);
  });

  it('filters by rol', () => {
    expect(filterUsuarios(rows, { rol: 'admin', estado: '' }, null)).toEqual([admin1]);
    expect(filterUsuarios(rows, { rol: 'operador', estado: '' }, null)).toEqual([
      operador1,
      operadorInactivo,
    ]);
  });

  it('filters by sucursal (matches any open assignment)', () => {
    expect(filterUsuarios(rows, { rol: '', estado: '' }, SUC_NORTE)).toEqual([admin1]);
    expect(filterUsuarios(rows, { rol: '', estado: '' }, SUC_SUR)).toEqual([operador1]);
  });

  it('filters by estado', () => {
    expect(filterUsuarios(rows, { rol: '', estado: 'inactivo' }, null)).toEqual([
      operadorInactivo,
    ]);
  });

  it('combines filters with AND semantics', () => {
    expect(
      filterUsuarios(rows, { rol: 'operador', estado: 'activo' }, null),
    ).toEqual([operador1]);
  });

  it('returns [] when no row matches every active filter', () => {
    expect(filterUsuarios(rows, { rol: 'admin', estado: '' }, SUC_SUR)).toEqual([]);
  });
});

function isolatedCache({ children }: { children: ReactNode }) {
  return createElement(
    SucursalProvider,
    null,
    createElement(
      SWRConfig,
      { value: { provider: () => new Map(), dedupingInterval: 0 } },
      createElement(MemoryRouter, null, children),
    ),
  );
}

describe('<UsuariosList /> — filter bar wiring', () => {
  beforeEach(() => {
    window.localStorage.removeItem('parkos.lastSelectedSucursal');
    mockedRaw.mockReset();
    mockedRaw.mockImplementation(async (input: unknown) => {
      const url = String(input);
      if (url.includes('/api/v1/admin/usuarios')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            items: [
              makeRow({
                uuid: UUID_ADMIN,
                email: 'admin@parkos.local',
                rol: 'admin',
                sucursales: [
                  { uuid_sucursal: SUC_NORTE, nombre: 'Norte', prefijo_nombre: 'NOR', vigente_desde: '2026-01-01' },
                  { uuid_sucursal: SUC_SUR, nombre: 'Sur', prefijo_nombre: 'SUR', vigente_desde: '2026-01-01' },
                ],
              }),
              makeRow({ uuid: UUID_OPERADOR, email: 'operador@parkos.local', rol: 'operador', sucursales: [] }),
            ],
            next_cursor: null,
          }),
          text: async () => '',
        } as Response;
      }
      if (url.includes('/api/v1/empresa/sucursal')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            items: [
              {
                uuid: SUC_NORTE,
                nombre: 'Norte',
                prefijo_nombre: 'NOR',
                direccion: null,
                telefono: null,
                ciudad: null,
                horario: null,
                uuid_tipo_sucursal: null,
                uuid_empresa: null,
                vigente_desde: '2026-01-01T00:00:00',
                vigente_hasta: null,
                estado: 'activo',
                created_at: '2026-01-01T00:00:00',
                created_by: null,
                sync_status: 'sincronizado',
              },
              {
                uuid: SUC_SUR,
                nombre: 'Sur',
                prefijo_nombre: 'SUR',
                direccion: null,
                telefono: null,
                ciudad: null,
                horario: null,
                uuid_tipo_sucursal: null,
                uuid_empresa: null,
                vigente_desde: '2026-01-01T00:00:00',
                vigente_hasta: null,
                estado: 'activo',
                created_at: '2026-01-01T00:00:00',
                created_by: null,
                sync_status: 'sincronizado',
              },
            ],
            next_cursor: null,
          }),
          text: async () => '',
        } as Response;
      }
      return { ok: true, status: 200, json: async () => ({}), text: async () => '' } as Response;
    });
  });

  it('shows every row by default and narrows down when a rol filter is picked', async () => {
    const user = userEvent.setup();
    render(<UsuariosList />, { wrapper: isolatedCache });

    await waitFor(() => {
      expect(screen.getByTestId(`admin-row-${UUID_ADMIN}`)).toBeInTheDocument();
      expect(screen.getByTestId(`admin-row-${UUID_OPERADOR}`)).toBeInTheDocument();
    });

    await user.selectOptions(screen.getByTestId('admin-filter-rol'), 'admin');

    expect(screen.getByTestId(`admin-row-${UUID_ADMIN}`)).toBeInTheDocument();
    expect(screen.queryByTestId(`admin-row-${UUID_OPERADOR}`)).not.toBeInTheDocument();
  });

  it('HU-X.8: when a branch is active globally (from /dashboard flow), the table is filtered to it and the combobox reflects it', async () => {
    // Operator flow: admin is on /dashboard with SUC_NORTE selected,
    // clicks the "Usuarios" link in the sidebar. The page should
    // mount already filtered to SUC_NORTE — the operator does NOT
    // need to pick the branch again. The prefijo_nombre is rendered
    // under the current-branch hint below the combobox.
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUC_NORTE);
    render(<UsuariosList />, { wrapper: isolatedCache });

    // The combobox input is present and the operator with assignments
    // in BOTH branches is shown only when the user picks SUC_NORTE or
    // SUC_SUR — here we only show the admin (the only one with a
    // Norte assignment); the operador has no assignments.
    await waitFor(() => {
      expect(screen.getByTestId(`admin-row-${UUID_ADMIN}`)).toBeInTheDocument();
      expect(screen.queryByTestId(`admin-row-${UUID_OPERADOR}`)).not.toBeInTheDocument();
    });
    // The combobox's "current" hint is the active branch.
    await waitFor(() => {
      expect(screen.getByTestId('admin-filter-sucursal-selected')).toBeInTheDocument();
    });
    expect(
      screen.getByTestId('admin-filter-sucursal-selected').textContent,
    ).toMatch(/Norte/);
  });

  it('HU-X.8: picking a different branch in the page combobox updates the global context and re-filters the table', async () => {
    // Write-through behavior (decided with the user, 2026-10-13): the
    // page combobox calls setSelected, which mirrors to the topbar
    // BranchSelector and to localStorage. The table re-filters
    // against the new branch — here we switch Norte → Sur.
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUC_NORTE);
    const user = userEvent.setup();
    render(<UsuariosList />, { wrapper: isolatedCache });

    // Start filtered to Norte — only admin (who has BOTH branches
    // in this test fixture) is shown; the operator has zero.
    await waitFor(() => {
      expect(screen.getByTestId(`admin-row-${UUID_ADMIN}`)).toBeInTheDocument();
      expect(screen.queryByTestId(`admin-row-${UUID_OPERADOR}`)).not.toBeInTheDocument();
    });

    // Open the listbox and pick the Sur option.
    const input = screen.getByTestId('admin-filter-sucursal');
    await user.click(input);
    const surOption = await screen.findByTestId(`admin-filter-sucursal-option-${SUC_SUR}`);
    await user.click(surOption);

    // The global context now points at SUC_SUR and the page mirrors it
    // (the operator with no assignments stays hidden; the admin stays
    // visible because the test fixture gives them both branches).
    await waitFor(() => {
      expect(window.localStorage.getItem('parkos.lastSelectedSucursal')).toBe(SUC_SUR);
    });
    expect(screen.getByTestId(`admin-row-${UUID_ADMIN}`)).toBeInTheDocument();
    expect(screen.queryByTestId(`admin-row-${UUID_OPERADOR}`)).not.toBeInTheDocument();
  });
});
