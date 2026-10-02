/**
 * `LogTransaccional.test.tsx` -- HU-F20.4 page-level integration tests.
 * Mirrors `alertas/pages/AlertasList.test.tsx`'s structure (SWR isolated
 * provider + `MemoryRouter`, api function mocked).
 *
 *  - T1: renders the fetched items.
 *  - T2: changing a filter re-fetches with that field set on the query.
 *  - T3: "Cargar más" appends the next page using the returned cursor.
 *  - T4: clicking "Ver detalle" navigates to `/auditoria/log/{uuid}`.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createElement, type ReactNode } from 'react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { SWRConfig } from 'swr';

const useSucursalesDirectorioMock = vi.fn();
vi.mock('@/features/sucursales/hooks/useSucursalesDirectorio', () => ({
  useSucursalesDirectorio: () => useSucursalesDirectorioMock(),
}));

vi.mock('../api/auditoriaApi', () => ({
  fetchLogTransaccional: vi.fn(),
}));

import { fetchLogTransaccional } from '../api/auditoriaApi';
import LogTransaccional from './LogTransaccional';

const mockedFetch = fetchLogTransaccional as ReturnType<typeof vi.fn>;

function row(uuid: string) {
  return {
    uuid,
    timestamp_evento: '2026-09-01T08:00:00',
    uuid_usuario: null,
    uuid_sucursal: '22222222-2222-2222-2222-222222222222',
    uuid_referencia: null,
    accion: 'crear',
    tabla_afectada: 'ingreso',
    datos_anteriores: null,
    datos_nuevos: { placa: 'ABC123' },
    hash_anterior: 'a'.repeat(64),
    hash_actual: 'b'.repeat(64),
  };
}

function wrapper({ children }: { children: ReactNode }): JSX.Element {
  return createElement(
    SWRConfig,
    { value: { provider: (): never => new Map() as never } },
    children,
  );
}

function renderPage(swrSalt: string) {
  return render(
    createElement(
      MemoryRouter,
      { initialEntries: ['/auditoria/log'] },
      createElement(
        Routes,
        null,
        createElement(Route, {
          path: '/auditoria/log',
          element: createElement(LogTransaccional, { swrSalt }),
        }),
        createElement(Route, {
          path: '/auditoria/log/:uuid',
          element: createElement('div', { 'data-testid': 'dest-detalle' }),
        }),
      ),
    ),
    { wrapper },
  );
}

describe('LogTransaccional', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('T1: renders the fetched items', async () => {
    useSucursalesDirectorioMock.mockReturnValue({
      sucursales: [{ uuid: '22222222-2222-2222-2222-222222222222', nombre: 'Norte' }],
    });
    mockedFetch.mockResolvedValue({ items: [row('a')], next_cursor: null });

    renderPage('t1');

    expect(await screen.findByTestId('log-transaccional-row-a')).toBeInTheDocument();
  });

  it('T2: changing the tabla filter re-fetches with tabla set on the query', async () => {
    useSucursalesDirectorioMock.mockReturnValue({ sucursales: [] });
    mockedFetch.mockResolvedValue({ items: [], next_cursor: null });

    const user = userEvent.setup();
    renderPage('t2');

    await waitFor(() => expect(mockedFetch).toHaveBeenCalledWith({ limit: 20 }));

    await user.type(screen.getByTestId('log-transaccional-filters-tabla'), 'ingreso');

    await waitFor(() =>
      expect(mockedFetch).toHaveBeenCalledWith(expect.objectContaining({ tabla: 'ingreso' })),
    );
  });

  it('T3: "Cargar más" appends the next page using the returned cursor', async () => {
    useSucursalesDirectorioMock.mockReturnValue({ sucursales: [] });
    mockedFetch.mockResolvedValueOnce({ items: [row('a')], next_cursor: 'cursor-1' });
    mockedFetch.mockResolvedValueOnce({ items: [row('b')], next_cursor: null });

    const user = userEvent.setup();
    renderPage('t3');

    expect(await screen.findByTestId('log-transaccional-row-a')).toBeInTheDocument();
    await user.click(screen.getByTestId('log-transaccional-load-more'));

    expect(await screen.findByTestId('log-transaccional-row-b')).toBeInTheDocument();
    expect(mockedFetch).toHaveBeenLastCalledWith(expect.objectContaining({ cursor: 'cursor-1' }));
  });

  it('T4: clicking "Ver detalle" navigates to /auditoria/log/{uuid} carrying the row via router state', async () => {
    useSucursalesDirectorioMock.mockReturnValue({ sucursales: [] });
    mockedFetch.mockResolvedValue({ items: [row('a')], next_cursor: null });

    const user = userEvent.setup();
    renderPage('t4');

    await user.click(await screen.findByTestId('log-transaccional-row-open-a'));

    await waitFor(() => expect(screen.getByTestId('dest-detalle')).toBeInTheDocument());
  });
});
