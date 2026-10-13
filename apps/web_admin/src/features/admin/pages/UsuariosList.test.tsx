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
    expect(filterUsuarios(rows, { rol: '', estado: '', search: '' }, null)).toEqual(rows);
  });

  it('filters by rol', () => {
    expect(filterUsuarios(rows, { rol: 'admin', estado: '', search: '' }, null)).toEqual([admin1]);
    expect(filterUsuarios(rows, { rol: 'operador', estado: '', search: '' }, null)).toEqual([
      operador1,
      operadorInactivo,
    ]);
  });

  it('filters by sucursal (matches any open assignment)', () => {
    expect(filterUsuarios(rows, { rol: '', estado: '', search: '' }, SUC_NORTE)).toEqual([admin1]);
    expect(filterUsuarios(rows, { rol: '', estado: '', search: '' }, SUC_SUR)).toEqual([operador1]);
  });

  it('filters by estado', () => {
    expect(filterUsuarios(rows, { rol: '', estado: 'inactivo', search: '' }, null)).toEqual([
      operadorInactivo,
    ]);
  });

  it('combines filters with AND semantics', () => {
    expect(
      filterUsuarios(rows, { rol: 'operador', estado: 'activo', search: '' }, null),
    ).toEqual([operador1]);
  });

  it('returns [] when no row matches every active filter', () => {
    expect(filterUsuarios(rows, { rol: 'admin', estado: '', search: '' }, SUC_SUR)).toEqual([]);
  });

  it('HU-F9: filters by search against email (case-insensitive)', () => {
    // The default makeRow() email is `user@parkos.local`, so we
    // override admin1 + operador1 with realistic emails to assert
    // case-insensitive matches.
    const adminWithEmail = makeRow({
      uuid: '1',
      email: 'admin@parkos.local',
      rol: 'admin',
      estado: 'activo',
      sucursales: [{ uuid_sucursal: SUC_NORTE, nombre: 'Norte', prefijo_nombre: 'NOR', vigente_desde: '2026-01-01' }],
    });
    const operadorWithEmail = makeRow({
      uuid: '2',
      email: 'operador@parkos.local',
      rol: 'operador',
      estado: 'activo',
      sucursales: [{ uuid_sucursal: SUC_SUR, nombre: 'Sur', prefijo_nombre: 'SUR', vigente_desde: '2026-01-01' }],
    });
    const richRows = [adminWithEmail, operadorWithEmail, operadorInactivo];
    // "ADMIN" (uppercase) matches admin@parkos.local
    expect(
      filterUsuarios(richRows, { rol: '', estado: '', search: 'ADMIN' }, null),
    ).toEqual([adminWithEmail]);
    // Full email also matches
    expect(
      filterUsuarios(richRows, { rol: '', estado: '', search: 'operador@parkos' }, null),
    ).toEqual([operadorWithEmail]);
  });

  it('HU-F9: filters by search against nombre + apellido (joined)', () => {
    // "QA Edit" matches the operador1 fixture (nombre overridden below
    // to "QA Edit Operador", apellido "Pruebas" -- joined with a
    // single space).
    const richOperador = makeRow({
      uuid: '2',
      rol: 'operador',
      estado: 'activo',
      nombre: 'QA Edit Operador',
      apellido: 'Pruebas',
      sucursales: [{ uuid_sucursal: SUC_SUR, nombre: 'Sur', prefijo_nombre: 'SUR', vigente_desde: '2026-01-01' }],
    });
    const richRows = [admin1, richOperador, operadorInactivo];
    expect(
      filterUsuarios(richRows, { rol: '', estado: '', search: 'qa edit' }, null),
    ).toEqual([richOperador]);
    // apellido only
    expect(
      filterUsuarios(richRows, { rol: '', estado: '', search: 'pruebas' }, null),
    ).toEqual([richOperador]);
  });

  it('HU-F9: empty search (whitespace only) disables the search filter', () => {
    expect(
      filterUsuarios(rows, { rol: '', estado: '', search: '   ' }, null),
    ).toEqual(rows);
  });

  it('HU-F9: search combines with rol/sucursal with AND semantics', () => {
    // "admin" + rol=operador -> only operador rows whose email OR
    // nombre includes "admin" -- operador1's email is operador@parkos
    // (no match), operadorInactivo has no email either. Both rows
    // share the search so neither matches -> [].
    expect(
      filterUsuarios(rows, { rol: 'operador', estado: '', search: 'admin' }, null),
    ).toEqual([]);
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
    // need to pick the branch again.
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
    // HU-fix-usuarios-alignment: the legacy "Actual: <nombre>" hint
    // paragraph under the combobox is gone (covered by the dedicated
    // test below); here we only need to assert the combobox is mounted
    // and bound to the active branch via the popup.
    expect(screen.getByTestId('admin-filter-sucursal')).toBeInTheDocument();
  });

  it('HU-fix-usuarios-alignment: no "Actual: <nombre>" hint is rendered under the branch combobox when a branch is selected', async () => {
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUC_NORTE);
    render(<UsuariosList />, { wrapper: isolatedCache });

    await waitFor(() => {
      expect(screen.getByTestId('admin-filter-sucursal')).toBeInTheDocument();
    });
    // The legacy data-testid must not be present (the hint paragraph
    // that used to carry it was removed in SucursalFilterCombobox).
    expect(screen.queryByTestId('admin-filter-sucursal-selected')).not.toBeInTheDocument();
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

  it('HU-F9: typing in the search input filters the table by email', async () => {
    const user = userEvent.setup();
    render(<UsuariosList />, { wrapper: isolatedCache });

    await waitFor(() => {
      expect(screen.getByTestId(`admin-row-${UUID_ADMIN}`)).toBeInTheDocument();
      expect(screen.getByTestId(`admin-row-${UUID_OPERADOR}`)).toBeInTheDocument();
    });

    const search = screen.getByTestId('admin-search-usuario');
    await user.type(search, 'operador');

    expect(screen.queryByTestId(`admin-row-${UUID_ADMIN}`)).not.toBeInTheDocument();
    expect(screen.getByTestId(`admin-row-${UUID_OPERADOR}`)).toBeInTheDocument();
  });

  it('HU-fix-usuarios-alignment: search input lives next to the rol/estado selects in the filtros row; branch combobox + nuevo button live in the page header', () => {
    render(<UsuariosList />, { wrapper: isolatedCache });

    // Filter row (admin-filtros) holds the three text/list filters that
    // narrow the already-fetched list: search + rol + estado.
    const search = screen.getByTestId('admin-search-usuario');
    const rol = screen.getByTestId('admin-filter-rol');
    const estado = screen.getByTestId('admin-filter-estado');
    const filtrosRow = search.closest('[data-testid="admin-filtros"]');
    expect(filtrosRow).toBeInTheDocument();
    expect(filtrosRow).toContainElement(rol);
    expect(filtrosRow).toContainElement(estado);

    // Page header actions cluster holds the global branch picker (which
    // writes through to the topbar) and the create-user button. The
    // search does NOT live here anymore.
    const combobox = screen.getByTestId('admin-filter-sucursal');
    const newButton = screen.getByTestId('admin-new');
    const headerActions = newButton.closest('[data-testid="page-header-actions"]');
    expect(headerActions).toBeInTheDocument();
    expect(headerActions).toContainElement(combobox);
    expect(headerActions).toContainElement(newButton);
    expect(headerActions).not.toContainElement(search);
  });

  it('HU-F9: "Todas las sucursales" option in the branch combobox clears the global selection and shows every user', async () => {
    // Start with a global branch selection so the table is filtered
    // and the combobox shows the "current" hint.
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUC_NORTE);
    const user = userEvent.setup();
    render(<UsuariosList />, { wrapper: isolatedCache });

    // Mount: filtered to SUC_NORTE — only admin (Norte assignment) is shown.
    await waitFor(() => {
      expect(screen.getByTestId(`admin-row-${UUID_ADMIN}`)).toBeInTheDocument();
      expect(screen.queryByTestId(`admin-row-${UUID_OPERADOR}`)).not.toBeInTheDocument();
    });

    // Open the picker and click the "Todas" pseudo-option.
    const input = screen.getByTestId('admin-filter-sucursal');
    await user.click(input);
    const allOption = await screen.findByTestId('admin-filter-sucursal-option-all');
    await user.click(allOption);

    // The global context is cleared (null in localStorage) and the
    // table re-fetches with no branch filter — every user is shown.
    await waitFor(() => {
      expect(window.localStorage.getItem('parkos.lastSelectedSucursal')).toBeNull();
    });
    expect(screen.getByTestId(`admin-row-${UUID_ADMIN}`)).toBeInTheDocument();
    expect(screen.getByTestId(`admin-row-${UUID_OPERADOR}`)).toBeInTheDocument();
  });
});
