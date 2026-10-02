/**
 * `AlertasList.test.tsx` -- HU-F19.5 page-level integration tests.
 *
 *  - T1: renders the fetched items.
 *  - T2: the sucursal filter dropdown only offers the actor's permitted
 *    sucursales (never the full directory).
 *  - T3: a row outside the permitted set is filtered out client-side
 *    (defense in depth, see the page's own docblock).
 *  - T4: clicking "Ver detalle" navigates to `/alertas/{uuid}`.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createElement, type ReactNode } from 'react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { SWRConfig } from 'swr';

const useAdminAuthMock = vi.fn();
vi.mock('@parkos/ui-kit/hooks', () => ({
  useAdminAuth: () => useAdminAuthMock(),
}));

const useSucursalesDirectorioMock = vi.fn();
vi.mock('@/features/sucursales/hooks/useSucursalesDirectorio', () => ({
  useSucursalesDirectorio: () => useSucursalesDirectorioMock(),
}));

vi.mock('../api/alertasApi', () => ({
  fetchAlertas: vi.fn(),
}));

import { fetchAlertas } from '../api/alertasApi';
import AlertasList from './AlertasList';

const mockedFetch = fetchAlertas as ReturnType<typeof vi.fn>;

const SUC_PERMITIDA = '22222222-2222-2222-2222-222222222222';
const SUC_NO_PERMITIDA = '33333333-3333-3333-3333-333333333333';

function alerta(uuid: string, uuidSucursal: string) {
  return {
    uuid,
    fecha_retencion_hasta: '2027-09-01',
    created_at: '2026-09-01T08:00:00',
    created_by: null,
    sync_status: null,
    sync_timestamp: null,
    sync_attempts: null,
    uuid_sucursal: uuidSucursal,
    uuid_usuario: null,
    uuid_arqueo: null,
    tipo_alerta: 'descuadre_critico',
    valor_diferencia_efectivo: null,
    valor_diferencia_datafono: null,
    uuid_alerta_padre: null,
    timestamp_evento: '2026-09-01T08:00:00',
    vigente_desde: '2026-09-01T08:00:00',
    vigente_hasta: null,
    estado: 'abierta',
    severity: 'critical',
  };
}

function wrapper({ children }: { children: ReactNode }): JSX.Element {
  return createElement(
    SWRConfig,
    { value: { provider: (): never => new Map() as never } },
    children,
  );
}

function renderPage() {
  return render(
    createElement(
      MemoryRouter,
      { initialEntries: ['/alertas'] },
      createElement(
        Routes,
        null,
        createElement(Route, { path: '/alertas', element: createElement(AlertasList) }),
        createElement(Route, { path: '/alertas/:uuid', element: createElement('div', { 'data-testid': 'dest-detalle' }) }),
      ),
    ),
    { wrapper },
  );
}

describe('AlertasList', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('T1 + T3: renders only the permitted-branch items', async () => {
    useAdminAuthMock.mockReturnValue({ sucursalUuids: [SUC_PERMITIDA] });
    useSucursalesDirectorioMock.mockReturnValue({
      sucursales: [
        { uuid: SUC_PERMITIDA, nombre: 'Sucursal Permitida' },
        { uuid: SUC_NO_PERMITIDA, nombre: 'Sucursal No Permitida' },
      ],
    });
    mockedFetch.mockResolvedValue({
      items: [alerta('a', SUC_PERMITIDA), alerta('b', SUC_NO_PERMITIDA)],
      next_cursor: null,
    });

    renderPage();

    expect(await screen.findByTestId('alertas-row-a')).toBeInTheDocument();
    expect(screen.queryByTestId('alertas-row-b')).not.toBeInTheDocument();
  });

  it('T2: the sucursal filter only offers permitted branches', async () => {
    useAdminAuthMock.mockReturnValue({ sucursalUuids: [SUC_PERMITIDA] });
    useSucursalesDirectorioMock.mockReturnValue({
      sucursales: [
        { uuid: SUC_PERMITIDA, nombre: 'Sucursal Permitida' },
        { uuid: SUC_NO_PERMITIDA, nombre: 'Sucursal No Permitida' },
      ],
    });
    mockedFetch.mockResolvedValue({ items: [], next_cursor: null });

    renderPage();

    const select = await screen.findByTestId('alertas-filters-sucursal');
    const optionValues = Array.from(select.querySelectorAll('option')).map((o) => o.getAttribute('value'));
    expect(optionValues).toContain(SUC_PERMITIDA);
    expect(optionValues).not.toContain(SUC_NO_PERMITIDA);
  });

  it('T4: clicking "Ver detalle" navigates to /alertas/{uuid}', async () => {
    const user = userEvent.setup();
    useAdminAuthMock.mockReturnValue({ sucursalUuids: [SUC_PERMITIDA] });
    useSucursalesDirectorioMock.mockReturnValue({
      sucursales: [{ uuid: SUC_PERMITIDA, nombre: 'Sucursal Permitida' }],
    });
    mockedFetch.mockResolvedValue({ items: [alerta('a', SUC_PERMITIDA)], next_cursor: null });

    renderPage();

    await user.click(await screen.findByTestId('alertas-row-open-a'));

    await waitFor(() => expect(screen.getByTestId('dest-detalle')).toBeInTheDocument());
  });
});
