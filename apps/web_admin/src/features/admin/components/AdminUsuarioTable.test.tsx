/**
 * `AdminUsuarioTable.test.tsx` — HU-F16.col, lazy branch panel.
 *
 * Why this test exists
 * --------------------
 * The column exists so the user can see which branches each row is
 * bound to without opening the modal. The contract we care about:
 *
 *   1. The header is present and positioned between Rol and Estado.
 *   2. No fetch fires on render — the N+1 we removed in commit 812badc
 *      must not come back through the table.
 *   3. The toggle flips aria-expanded and the panel mounts on expand.
 *   4. The panel projects the friendly name from the shared directory
 *      cache; an unknown uuid falls back to the short prefix instead
 *      of crashing.
 *   5. Errors are surfaced inline, not swallowed.
 *   6. The Asignar sucursales action still works alongside the new
 *      toggle — we did not break the modal entry point.
 *
 * The mock is at the fetch layer, not at the hook layer. That is the
 * seam `useAdminUsuarioSucursales` and `useSucursalesDirectorio` both
 * go through, and it lets the test exercise the real SWR keys.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createElement, type ReactNode } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { SWRConfig } from 'swr';

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
const SUC_FANTASMA = 'cccc3333-cccc-cccc-cccc-cccccccccccc';

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
    ...overrides,
  };
}

const SUCURSAL_NORTE = {
  uuid: SUC_NORTE,
  nombre: 'Sucursal Norte',
  direccion: 'Calle 100',
  telefono: '+57 1 0000',
  prefijo_nombre: 'NOR',
  ciudad: 'Bogota',
  horario: '24/7',
  uuid_tipo_sucursal: null,
  uuid_empresa: null,
  vigente_desde: '2026-01-01T00:00:00Z',
  vigente_hasta: null,
  estado: 'activo',
  created_at: '2026-01-01T00:00:00Z',
  created_by: null,
  sync_status: null,
};

const SUCURSAL_SUR = {
  ...SUCURSAL_NORTE,
  uuid: SUC_SUR,
  nombre: 'Sucursal Sur',
  prefijo_nombre: 'SUR',
};

function okResponse(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body } as unknown as Response;
}

function requestedUrls(): string[] {
  return mockedRaw.mock.calls.map((call) => String(call[0]));
}

/**
 * Per-test SWR cache. Without this, fetches written by a previous test
 * would satisfy the next one — same mechanism that caused the original
 * SWR-key shape collision.
 */
function isolatedCache({ children }: { children: ReactNode }) {
  return createElement(
    SWRConfig,
    { value: { provider: () => new Map(), dedupingInterval: 0 } },
    children,
  );
}

function renderTable(
  rows: AdminUsuarioRead[],
  expandedUserUuid: string | null = null,
) {
  const onAssign = vi.fn();
  const onToggle = vi.fn();
  const view = render(
    <AdminUsuarioTable
      rows={rows}
      isLoading={false}
      expandedUserUuid={expandedUserUuid}
      onToggleExpanded={onToggle}
      onAssignSucursales={onAssign}
    />,
    { wrapper: isolatedCache },
  );
  return { ...view, onAssign, onToggle };
}

beforeEach(() => {
  mockedRaw.mockReset();
});

describe('AdminUsuarioTable — Sucursales column', () => {
  it('renders the Sucursales header between Rol and Estado', () => {
    mockedRaw.mockResolvedValue(okResponse([SUCURSAL_NORTE]));
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
    mockedRaw.mockResolvedValue(okResponse([SUCURSAL_NORTE]));
    renderTable([makeRow()]);

    const perUserUrls = requestedUrls().filter((u) =>
      u.includes(`/api/v1/admin/usuarios/${USER_A}/sucursales`),
    );
    expect(perUserUrls).toHaveLength(0);
  });

  it('renders a Ver button per row with aria-expanded=false', () => {
    mockedRaw.mockResolvedValue(okResponse([SUCURSAL_NORTE]));
    renderTable([makeRow()]);

    const btn = screen.getByTestId(`admin-row-${USER_A}-toggle-sucursales`);
    expect(btn).toBeInTheDocument();
    expect(btn.textContent).toMatch(/Ver/);
    expect(btn.getAttribute('aria-expanded')).toBe('false');
    expect(btn.getAttribute('aria-controls')).toBe(`admin-row-${USER_A}-panel`);
  });

  it('fetches the per-user assignments exactly once when the cell is expanded', async () => {
    mockedRaw.mockImplementation(async (url) => {
      const s = String(url);
      if (s === '/api/v1/empresa/sucursal?limit=200') {
        return okResponse({ items: [SUCURSAL_NORTE], next_cursor: null });
      }
      if (s === `/api/v1/admin/usuarios/${USER_A}/sucursales`) {
        return okResponse([{ uuid_sucursal: SUC_NORTE }]);
      }
      throw new Error(`unexpected URL in test: ${s}`);
    });

    renderTable([makeRow()], USER_A);

    await waitFor(() => {
      const calls = requestedUrls().filter(
        (u) => u === `/api/v1/admin/usuarios/${USER_A}/sucursales`,
      );
      expect(calls).toHaveLength(1);
    });

    // The button label flips to "Ocultar" once expanded.
    const btn = screen.getByTestId(`admin-row-${USER_A}-toggle-sucursales`);
    expect(btn.textContent).toMatch(/Ocultar/);
    expect(btn.getAttribute('aria-expanded')).toBe('true');

    // The chip renders with the friendly name from the directory.
    await waitFor(() => {
      expect(
        screen.getByTestId(`admin-row-${USER_A}-chip-${SUC_NORTE}`),
      ).toHaveTextContent('Sucursal Norte');
    });
  });

  it('falls back to the short uuid when the directory has no name for a branch', async () => {
    mockedRaw.mockImplementation(async (url) => {
      const s = String(url);
      if (s === '/api/v1/empresa/sucursal?limit=200') {
        return okResponse({
          items: [SUCURSAL_NORTE, SUCURSAL_SUR],
          next_cursor: null,
        });
      }
      if (s === `/api/v1/admin/usuarios/${USER_A}/sucursales`) {
        return okResponse([
          { uuid_sucursal: SUC_FANTASMA },
          { uuid_sucursal: SUC_NORTE },
        ]);
      }
      throw new Error(`unexpected URL in test: ${s}`);
    });

    renderTable([makeRow()], USER_A);

    await waitFor(() => {
      expect(
        screen.getByTestId(`admin-row-${USER_A}-chip-${SUC_FANTASMA}`),
      ).toHaveTextContent(SUC_FANTASMA.slice(0, 8));
    });
    await waitFor(() => {
      expect(
        screen.getByTestId(`admin-row-${USER_A}-chip-${SUC_NORTE}`),
      ).toHaveTextContent('Sucursal Norte');
    });
  });

  it('surfaces an inline error when the per-user fetch fails', async () => {
    mockedRaw.mockImplementation(async (url) => {
      const s = String(url);
      if (s === '/api/v1/empresa/sucursal?limit=200') {
        return okResponse({ items: [SUCURSAL_NORTE], next_cursor: null });
      }
      if (s === `/api/v1/admin/usuarios/${USER_A}/sucursales`) {
        throw new Error('network down');
      }
      throw new Error(`unexpected URL in test: ${s}`);
    });

    renderTable([makeRow()], USER_A);

    await waitFor(() => {
      expect(
        screen.getByTestId(`admin-row-${USER_A}-panel-error`),
      ).toBeInTheDocument();
    });
  });

  it('still shows the Asignar sucursales action alongside the new toggle', () => {
    mockedRaw.mockResolvedValue(okResponse([SUCURSAL_NORTE]));
    renderTable([makeRow()]);

    expect(screen.getByTestId(`admin-row-${USER_A}-assign`)).toBeInTheDocument();
    expect(
      screen.getByTestId(`admin-row-${USER_A}-toggle-sucursales`),
    ).toBeInTheDocument();
  });
});
