/**
 * `AnulacionesList.test.tsx` -- HU-F20.3 page-level integration tests.
 *
 *  - T1: renders the fetched items.
 *  - T2: clicking "Ver detalle" navigates to `/anulaciones/{uuid}`.
 *  - T3: an empty result set renders the empty state.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createElement, type ReactNode } from 'react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { SWRConfig } from 'swr';

vi.mock('../api/anulacionesApi', () => ({
  fetchAnulaciones: vi.fn(),
}));

import { fetchAnulaciones } from '../api/anulacionesApi';
import AnulacionesList from './AnulacionesList';

const mockedFetch = fetchAnulaciones as ReturnType<typeof vi.fn>;

function anulacion(uuid: string, overrides: Partial<Record<string, unknown>> = {}) {
  return {
    uuid,
    fecha_retencion_hasta: '2027-09-01',
    created_at: '2026-09-01T08:00:00',
    created_by: null,
    sync_status: null,
    sync_timestamp: null,
    sync_attempts: null,
    uuid_sucursal: '22222222-2222-2222-2222-222222222222',
    tipo_anulable: 'ingreso',
    uuid_ingreso: '33333333-3333-3333-3333-333333333333',
    uuid_salida: null,
    uuid_usuario: null,
    motivo: 'Placa duplicada',
    uuid_anulacion_padre: null,
    timestamp_evento: '2026-09-01T08:00:00',
    vigente_desde: '2026-09-01T08:00:00',
    vigente_hasta: null,
    estado: 'iniciada',
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
      { initialEntries: ['/anulaciones'] },
      createElement(
        Routes,
        null,
        createElement(Route, { path: '/anulaciones', element: createElement(AnulacionesList) }),
        createElement(Route, {
          path: '/anulaciones/:uuid',
          element: createElement('div', { 'data-testid': 'dest-detalle' }),
        }),
      ),
    ),
    { wrapper },
  );
}

describe('AnulacionesList', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('T1: renders the fetched items', async () => {
    mockedFetch.mockResolvedValue({ items: [anulacion('a')], next_cursor: null });

    renderPage();

    expect(await screen.findByTestId('anulaciones-row-a')).toBeInTheDocument();
    expect(screen.getByTestId('anulaciones-row-a')).toHaveTextContent('ingreso');
  });

  it('T2: clicking "Ver detalle" navigates to /anulaciones/{uuid}', async () => {
    const user = userEvent.setup();
    mockedFetch.mockResolvedValue({ items: [anulacion('a')], next_cursor: null });

    renderPage();

    await user.click(await screen.findByTestId('anulaciones-row-open-a'));

    await waitFor(() => expect(screen.getByTestId('dest-detalle')).toBeInTheDocument());
  });

  it('T3: an empty result set renders the empty state', async () => {
    mockedFetch.mockResolvedValue({ items: [], next_cursor: null });

    renderPage();

    expect(await screen.findByTestId('anulaciones-empty')).toBeInTheDocument();
  });
});
