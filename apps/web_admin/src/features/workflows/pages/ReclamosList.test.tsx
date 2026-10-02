/**
 * `ReclamosList.test.tsx` -- HU-F20.3 page-level integration tests.
 * Mirrors `AnulacionesList.test.tsx`.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createElement, type ReactNode } from 'react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { SWRConfig } from 'swr';

vi.mock('../api/reclamosApi', () => ({
  fetchReclamos: vi.fn(),
}));

import { fetchReclamos } from '../api/reclamosApi';
import ReclamosList from './ReclamosList';

const mockedFetch = fetchReclamos as ReturnType<typeof vi.fn>;

function reclamo(uuid: string, overrides: Partial<Record<string, unknown>> = {}) {
  return {
    uuid,
    created_at: '2026-09-01T08:00:00',
    created_by: null,
    sync_status: null,
    sync_timestamp: null,
    sync_attempts: null,
    uuid_sucursal: '22222222-2222-2222-2222-222222222222',
    tipo_reclamable: 'factura',
    uuid_reclamable: '33333333-3333-3333-3333-333333333333',
    motivo: 'Cobro duplicado',
    uuid_reclamo_padre: null,
    timestamp_evento: '2026-09-01T08:00:00',
    vigente_desde: '2026-09-01T08:00:00',
    vigente_hasta: null,
    estado: 'recibido',
    ...overrides,
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
      { initialEntries: ['/reclamos'] },
      createElement(
        Routes,
        null,
        createElement(Route, { path: '/reclamos', element: createElement(ReclamosList) }),
        createElement(Route, {
          path: '/reclamos/:uuid',
          element: createElement('div', { 'data-testid': 'dest-detalle' }),
        }),
      ),
    ),
    { wrapper },
  );
}

describe('ReclamosList', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('T1: renders the fetched items', async () => {
    mockedFetch.mockResolvedValue({ items: [reclamo('a')], next_cursor: null });

    renderPage();

    expect(await screen.findByTestId('reclamos-row-a')).toBeInTheDocument();
    expect(screen.getByTestId('reclamos-row-a')).toHaveTextContent('factura');
  });

  it('T2: clicking "Ver detalle" navigates to /reclamos/{uuid}', async () => {
    const user = userEvent.setup();
    mockedFetch.mockResolvedValue({ items: [reclamo('a')], next_cursor: null });

    renderPage();

    await user.click(await screen.findByTestId('reclamos-row-open-a'));

    await waitFor(() => expect(screen.getByTestId('dest-detalle')).toBeInTheDocument());
  });

  it('T3: an empty result set renders the empty state', async () => {
    mockedFetch.mockResolvedValue({ items: [], next_cursor: null });

    renderPage();

    expect(await screen.findByTestId('reclamos-empty')).toBeInTheDocument();
  });
});
