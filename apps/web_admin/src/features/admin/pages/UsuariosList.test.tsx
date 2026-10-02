/**
 * `UsuariosList.test.tsx` — HU-F16.2 filter tests (rol/sucursal/estado)
 * + the create-wizard swap-in smoke test.
 *
 * The filtering rule itself is exercised directly against the exported
 * pure `filterUsuarios` helper (fast, no rendering/mocking needed). A
 * lighter page-level smoke test then renders `<UsuariosList />` with the
 * fetch layer mocked (same seam as `AdminUsuarioTable.test.tsx`) to
 * confirm the filter controls are wired to the table.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createElement, type ReactNode } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SWRConfig } from 'swr';
import { MemoryRouter } from 'react-router-dom';

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

  it('returns every row when every filter is "" (no filter)', () => {
    expect(filterUsuarios(rows, { rol: '', sucursal: '', estado: '' })).toEqual(rows);
  });

  it('filters by rol', () => {
    expect(filterUsuarios(rows, { rol: 'admin', sucursal: '', estado: '' })).toEqual([admin1]);
    expect(filterUsuarios(rows, { rol: 'operador', sucursal: '', estado: '' })).toEqual([
      operador1,
      operadorInactivo,
    ]);
  });

  it('filters by sucursal (matches any open assignment)', () => {
    expect(filterUsuarios(rows, { rol: '', sucursal: SUC_NORTE, estado: '' })).toEqual([admin1]);
    expect(filterUsuarios(rows, { rol: '', sucursal: SUC_SUR, estado: '' })).toEqual([operador1]);
  });

  it('filters by estado', () => {
    expect(filterUsuarios(rows, { rol: '', sucursal: '', estado: 'inactivo' })).toEqual([
      operadorInactivo,
    ]);
  });

  it('combines filters with AND semantics', () => {
    expect(
      filterUsuarios(rows, { rol: 'operador', sucursal: '', estado: 'activo' }),
    ).toEqual([operador1]);
  });

  it('returns [] when no row matches every active filter', () => {
    expect(filterUsuarios(rows, { rol: 'admin', sucursal: SUC_SUR, estado: '' })).toEqual([]);
  });
});

function isolatedCache({ children }: { children: ReactNode }) {
  return createElement(
    SWRConfig,
    { value: { provider: () => new Map(), dedupingInterval: 0 } },
    createElement(MemoryRouter, null, children),
  );
}

describe('<UsuariosList /> — filter bar wiring', () => {
  beforeEach(() => {
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
          json: async () => ({ items: [], next_cursor: null }),
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
});
