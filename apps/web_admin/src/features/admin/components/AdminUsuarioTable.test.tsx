/**
 * `AdminUsuarioTable.test.tsx` — HU-F16.col, INLINE branch chips.
 *
 * Why this test exists
 * --------------------
 * The Sucursales column was first introduced as a lazy disclosure
 * (commit 9330f93) and then refactored to inline render once the
 * backend started embedding `user.sucursales` on the list payload.
 * The contract we now care about:
 *
 *   1. The header is present and positioned between Rol and Estado.
 *   2. No fetch fires on render — the backend already shipped the
 *      assignments inline, so the table does not call
 *      `/api/v1/admin/usuarios/{uuid}/sucursales` per row.
 *   3. Each open branch assignment renders as a chip with the
 *      friendly name from `s.nombre`.
 *   4. When the backend payload has `nombre=null` for a closed
 *      branch, the chip falls back to `prefijo_nombre`, then to the
 *      short uuid prefix (no crash, just a readable identifier).
 *   5. A user with no assignments renders the muted "Sin sucursales"
 *      span, not an empty `<ul>`.
 *   6. The Asignar sucursales action still works alongside the chips
 *      — we did not break the modal entry point.
 *
 * The mock is at the fetch layer so the test exercises the real SWR
 * keys via `parkosFetchRaw` (the same seam `useAdminUsuarios` and
 * `useSucursalesDirectorio` go through).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createElement, type ReactNode } from 'react';
import { render, screen } from '@testing-library/react';
import { SWRConfig } from 'swr';
import { MemoryRouter } from 'react-router-dom';

vi.mock('@parkos/ui-kit/fetch', () => ({
  parkosFetchRaw: vi.fn(),
  parkosFetch: vi.fn(),
}));

import { parkosFetchRaw } from '@parkos/ui-kit/fetch';

import { AdminUsuarioTable } from './AdminUsuarioTable';
import type { AdminUsuarioRead } from '../api/adminUsuarioSchema';

const mockedRaw = vi.mocked(parkosFetchRaw);

const USER_A = '83ef5d9f-dd65-47e3-9b13-50deed0f03d3';
const SUC_NORTE = 'aaaa1111-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
const SUC_SUR = 'bbbb2222-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
const SUC_PREFIX = 'cccc3333-cccc-cccc-cccc-cccccccccccc';
const SUC_FANTASMA = 'dddd4444-dddd-dddd-dddd-dddddddddddd';

function makeRow(overrides: Partial<AdminUsuarioRead> = {}): AdminUsuarioRead {
  return {
    uuid: USER_A,
    email: 'andres25ortega@gmail.com',
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

function requestedUrls(): string[] {
  return mockedRaw.mock.calls.map((call) => String(call[0]));
}

/**
 * Per-test SWR cache + a Router. Without this, fetches written by a
 * previous test would satisfy the next one — same mechanism that caused
 * the original SWR-key shape collision.
 *
 * The Router is required because the table renders the detail `<Link>`
 * on the email cell. `<Link>` outside a Router throws, so any future
 * addition of a router-aware element to this table has to keep this
 * wrapper in place.
 */
function isolatedCache({ children }: { children: ReactNode }) {
  return createElement(
    SWRConfig,
    { value: { provider: () => new Map(), dedupingInterval: 0 } },
    createElement(MemoryRouter, null, children),
  );
}

function renderTable(rows: AdminUsuarioRead[]) {
  const onAssign = vi.fn();
  const view = render(
    <AdminUsuarioTable
      rows={rows}
      isLoading={false}
      onAssignSucursales={onAssign}
    />,
    { wrapper: isolatedCache },
  );
  return { ...view, onAssign };
}

beforeEach(() => {
  mockedRaw.mockReset();
});

describe('AdminUsuarioTable — Sucursales column (inline chips)', () => {
  it('renders the Sucursales header between Rol and Estado', () => {
    renderTable([makeRow()]);

    const headers = screen.getAllByRole('columnheader');
    const labels = headers.map((h) => h.textContent ?? '');
    const rolIdx = labels.findIndex((t) => t.includes('Rol'));
    const sucIdx = labels.findIndex((t) => t.includes('Sucursales'));
    const estIdx = labels.findIndex((t) => t.includes('Estado'));

    expect(rolIdx).toBeGreaterThanOrEqual(0);
    expect(sucIdx).toBeGreaterThanOrEqual(0);
    expect(estIdx).toBeGreaterThanOrEqual(0);
    expect(rolIdx).toBeLessThan(sucIdx);
    expect(sucIdx).toBeLessThan(estIdx);
  });

  it('does NOT fire any per-user assignment request on initial render', () => {
    renderTable([
      makeRow({
        sucursales: [
          {
            uuid_sucursal: SUC_NORTE,
            nombre: 'Sucursal Norte',
            prefijo_nombre: 'NOR',
            vigente_desde: '2026-01-01T00:00:00Z',
          },
        ],
      }),
    ]);

    const perUserUrls = requestedUrls().filter((u) =>
      u.includes(`/api/v1/admin/usuarios/${USER_A}/sucursales`),
    );
    expect(perUserUrls).toHaveLength(0);
  });

  it('renders each open branch as a chip with the friendly name from the payload', () => {
    renderTable([
      makeRow({
        sucursales: [
          {
            uuid_sucursal: SUC_NORTE,
            nombre: 'Sucursal Norte',
            prefijo_nombre: 'NOR',
            vigente_desde: '2026-01-01T00:00:00Z',
          },
          {
            uuid_sucursal: SUC_SUR,
            nombre: 'Sucursal Sur',
            prefijo_nombre: 'SUR',
            vigente_desde: '2026-01-01T00:00:00Z',
          },
        ],
      }),
    ]);

    const norte = screen.getByTestId(`admin-row-${USER_A}-chip-${SUC_NORTE}`);
    const sur = screen.getByTestId(`admin-row-${USER_A}-chip-${SUC_SUR}`);
    expect(norte).toHaveTextContent('Sucursal Norte');
    expect(sur).toHaveTextContent('Sucursal Sur');
  });

  it('renders the "Sin sucursales" span when the user has no open assignments', () => {
    renderTable([makeRow({ sucursales: [] })]);

    expect(
      screen.getByTestId(`admin-row-${USER_A}-sucursales-empty`),
    ).toHaveTextContent(/Sin sucursales/i);
    // No chips should render for an empty row.
    expect(
      screen.queryByTestId(`admin-row-${USER_A}-sucursales-chips`),
    ).not.toBeInTheDocument();
  });

  it('falls back to prefijo_nombre then short uuid when nombre is null', () => {
    renderTable([
      makeRow({
        sucursales: [
          {
            uuid_sucursal: SUC_PREFIX,
            nombre: null,
            prefijo_nombre: 'PREFIX',
            vigente_desde: '2026-01-01T00:00:00Z',
          },
          {
            uuid_sucursal: SUC_FANTASMA,
            nombre: null,
            prefijo_nombre: null,
            vigente_desde: '2026-01-01T00:00:00Z',
          },
        ],
      }),
    ]);

    expect(
      screen.getByTestId(`admin-row-${USER_A}-chip-${SUC_PREFIX}`),
    ).toHaveTextContent('PREFIX');
    expect(
      screen.getByTestId(`admin-row-${USER_A}-chip-${SUC_FANTASMA}`),
    ).toHaveTextContent(SUC_FANTASMA.slice(0, 8));
  });

  it('still shows the Asignar sucursales action alongside the chips', () => {
    renderTable([
      makeRow({
        sucursales: [
          {
            uuid_sucursal: SUC_NORTE,
            nombre: 'Sucursal Norte',
            prefijo_nombre: 'NOR',
            vigente_desde: '2026-01-01T00:00:00Z',
          },
        ],
      }),
    ]);

    expect(screen.getByTestId(`admin-row-${USER_A}-assign`)).toBeInTheDocument();
    expect(
      screen.getByTestId(`admin-row-${USER_A}-chip-${SUC_NORTE}`),
    ).toBeInTheDocument();
  });
});
