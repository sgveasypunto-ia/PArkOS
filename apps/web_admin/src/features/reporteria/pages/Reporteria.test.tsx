/**
 * `<Reporteria />` — page-level integration tests (HU-F17.x, HU-X.8
 * follow-up).
 *
 * The component fans out to six different endpoints (ingresos, salidas,
 * ocupacion, operacional, ocupacion heatmap, plus the
 * `/api/v1/sucursales` lookup). The single page-level test below pins
 * the HU-X.8 behaviour — the inline branch combobox renders with the
 * active branch selected and writes through to the global
 * SucursalContext. Per-tab behaviour is covered in the per-table
 * component tests (EstanciaPanel.test.tsx, IngresosTable.test, etc).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createElement, type ReactNode } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SWRConfig } from 'swr';
import { MemoryRouter } from 'react-router-dom';

import { SucursalProvider } from '@/lib/sucursal-context';

vi.mock('@/lib/fetch', () => ({
  parkosFetchRaw: vi.fn(),
}));

import { parkosFetchRaw } from '@/lib/fetch';

import Reporteria from './Reporteria';

const mockedRaw = vi.mocked(parkosFetchRaw);

const SUC_NORTE = '11111111-1111-1111-1111-111111111111';
const SUC_SUR = '22222222-2222-2222-2222-222222222222';

function wrapper({ children }: { children: ReactNode }): JSX.Element {
  const configValue = { provider: (): never => new Map() as never };
  return createElement(
    SucursalProvider,
    null,
    createElement(SWRConfig, { value: configValue }, children),
  );
}

function fullWrapper({ children }: { children: ReactNode }): JSX.Element {
  return createElement(MemoryRouter, null, createElement(wrapper, { children }));
}

beforeEach(() => {
  window.localStorage.removeItem('parkos.lastSelectedSucursal');
  mockedRaw.mockReset();
  mockedRaw.mockImplementation(async (input: unknown) => {
    const url = String(input);
    if (url.includes('/api/v1/sucursales')) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          items: [
            { uuid: SUC_NORTE, nombre: 'Norte', prefijo_nombre: 'NOR' },
            { uuid: SUC_SUR, nombre: 'Sur', prefijo_nombre: 'SUR' },
          ],
        }),
        text: async () => '',
      } as Response;
    }
    // Every reporteria endpoint returns an empty payload — the
    // page-level test only cares about the branch combobox wiring.
    if (url.includes('/api/v1/operacion/')) {
      return {
        ok: true,
        status: 200,
        json: async () => (url.includes('ocupacion') ? { cupo: 0, activos: 0, disponibles: 0 } : []),
        text: async () => '',
      } as Response;
    }
    if (url.includes('/api/v1/admin/reporteria/')) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          ingresos: 0,
          ingresos_activos: 0,
          salidas: 0,
          facturas: 0,
          monto_facturado: '0',
          monto_cobrado: '0',
          tiempos_estancia: [],
          data: [],
          sucursales: [],
        }),
        text: async () => '',
      } as Response;
    }
    return { ok: true, status: 200, json: async () => ({}), text: async () => '' } as Response;
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.removeItem('parkos.lastSelectedSucursal');
});

describe('Reporteria (operacional) page — HU-X.8 branch combobox', () => {
  it('R19: when a branch is active globally, the header combobox shows it and the subtitle names it', async () => {
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUC_NORTE);
    render(<Reporteria />, { wrapper: fullWrapper });
    await waitFor(() => {
      expect(screen.getByTestId('reporteria-branch-combobox')).toBeInTheDocument();
    });
    // The subtitle carries the branch name in parens (this is the
    // canonical "which branch is active" surface -- the legacy
    // "Actual: <nombre>" hint paragraph was removed by
    // HU-fix-usuarios-alignment, so we no longer pin that data-testid
    // here).
    await waitFor(() => {
      expect(screen.getByTestId('reporteria-branch-name')).toBeInTheDocument();
    });
    expect(screen.getByTestId('reporteria-branch-name').textContent).toMatch(
      /Norte/,
    );
  });

  it('R20: picking a different branch in the page combobox updates the global context (write-through)', async () => {
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUC_NORTE);
    const user = userEvent.setup();
    render(<Reporteria />, { wrapper: fullWrapper });
    await waitFor(() => {
      expect(screen.getByTestId('reporteria-branch-combobox')).toBeInTheDocument();
    });
    const input = screen.getByTestId('reporteria-branch-combobox');
    await user.click(input);
    const surOption = await screen.findByTestId(
      `reporteria-branch-combobox-option-${SUC_SUR}`,
    );
    await user.click(surOption);
    // Write-through: the global context (localStorage) now points
    // at SUC_SUR and the subtitle mirrors it.
    await waitFor(() => {
      expect(window.localStorage.getItem('parkos.lastSelectedSucursal')).toBe(
        SUC_SUR,
      );
    });
    expect(screen.getByTestId('reporteria-branch-name').textContent).toMatch(
      /Sur/,
    );
  });

  it('HU-fix-reporteria-todas-sucursales: "Todas las sucursales" picks the cross-branch aggregate; the same page layout (KPIs panel + tabs + heatmap) renders with branch-scoped endpoints called without uuid_sucursal', async () => {
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUC_NORTE);
    const user = userEvent.setup();
    const seenUrls: string[] = [];
    const baseImpl = mockedRaw.getMockImplementation();
    mockedRaw.mockImplementation(async (input: unknown) => {
      const url = String(input);
      seenUrls.push(url);
      return baseImpl ? baseImpl(input) : ({ ok: true, status: 200, json: async () => ({}), text: async () => '' } as Response);
    });
    render(<Reporteria />, { wrapper: fullWrapper });

    const input = screen.getByTestId('reporteria-branch-combobox');
    await user.click(input);
    const allOption = await screen.findByTestId(
      'reporteria-branch-combobox-option-all',
    );
    await user.click(allOption);

    // The global selection is cleared (null) and the SAME page layout
    // renders with cross-branch data (no "Seleccioná una sucursal"
    // placeholder anymore -- the user reported that as a bug).
    await waitFor(() => {
      expect(window.localStorage.getItem('parkos.lastSelectedSucursal')).toBeNull();
    });
    expect(screen.queryByTestId('reporteria-no-branch')).not.toBeInTheDocument();
    // The totals panel + tabs are present.
    expect(screen.getByTestId('reporteria-totales-section')).toBeInTheDocument();
    expect(screen.getByTestId('reporteria-tab-ingresos')).toBeInTheDocument();
    expect(screen.getByTestId('reporteria-tab-salidas')).toBeInTheDocument();
    expect(screen.getByTestId('reporteria-tab-ocupacion')).toBeInTheDocument();
    // The cross-branch heatmap lives inside the Ocupacion tab's
    // TabsContent (it is always cross-branch, by design); activate
    // the tab to assert it is wired up.
    await user.click(screen.getByTestId('reporteria-tab-ocupacion'));
    expect(screen.getByTestId('reporteria-heatmap-section')).toBeInTheDocument();
    // The subtitle badge now reads "Todas las sucursales".
    expect(screen.getByTestId('reporteria-branch-name').textContent).toMatch(
      /Todas las sucursales/,
    );

    // The branch-scoped admin reporteria endpoints were re-called
    // WITHOUT a ``uuid_sucursal`` query param after "Todas" was
    // picked -- the cross-branch aggregate path on the backend
    // (HU-fix-reporteria-todas-sucursales). Use ``findLast`` because
    // the same endpoint was also called with the previous branch
    // selected (SUC_NORTE) before the picker fired.
    await waitFor(() => {
      const allOperacionalUrl = [...seenUrls]
        .reverse()
        .find((u) => u.startsWith('/api/v1/admin/reporteria/operacional'));
      expect(allOperacionalUrl).toBeDefined();
      expect(allOperacionalUrl).not.toMatch(/uuid_sucursal=/);
    });

    await waitFor(() => {
      const allOcupacionUrl = [...seenUrls]
        .reverse()
        .find((u) => u.startsWith('/api/v1/operacion/ocupacion'));
      // The /operacion/ocupacion endpoint is called either with no
      // params at all (cross-branch) or without uuid_sucursal=.
      expect(allOcupacionUrl).toBeDefined();
      expect(allOcupacionUrl).not.toMatch(/uuid_sucursal=/);
    });
  });
});
