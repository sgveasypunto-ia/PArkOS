/**
 * `AnulacionDetalle.test.tsx` -- HU-F20.3 detail page integration tests.
 * Mirrors `alertas/pages/AlertaDetalle.test.tsx`'s depth, plus an
 * explicit chain-walking test (the "walk `uuid_anulacion_padre`
 * backwards" gap workaround, see `useAnulacionChain.ts`).
 *
 *  - T1: renders the anulación's data once `fetchAnulacion` resolves.
 *  - T2: walks `uuid_anulacion_padre` backwards to build the chain.
 *  - T3: the "Aprobar" action opens the modal, submits, and the page
 *    reflects the updated `estado` without a page reload.
 *  - T4: a terminal (`ejecutada`) anulación shows no transition buttons.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createElement, type ReactNode } from 'react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { SWRConfig } from 'swr';
import type * as AnulacionesApiModule from '../api/anulacionesApi';

vi.mock('../api/anulacionesApi', async () => {
  const actual = await vi.importActual<typeof AnulacionesApiModule>('../api/anulacionesApi');
  return { ...actual, fetchAnulacion: vi.fn(), transicionarAnulacion: vi.fn() };
});

import { fetchAnulacion, transicionarAnulacion } from '../api/anulacionesApi';
import AnulacionDetalle from './AnulacionDetalle';

const mockedFetch = fetchAnulacion as ReturnType<typeof vi.fn>;
const mockedTransicionar = transicionarAnulacion as ReturnType<typeof vi.fn>;

const UUID = '11111111-1111-1111-1111-111111111111';
const PADRE_UUID = '55555555-5555-5555-5555-555555555555';

function baseAnulacion(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    uuid: UUID,
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
    uuid_usuario: '44444444-4444-4444-4444-444444444444',
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

function renderDetalle() {
  return render(
    createElement(
      MemoryRouter,
      { initialEntries: [`/anulaciones/${UUID}`] },
      createElement(
        Routes,
        null,
        createElement(Route, {
          path: '/anulaciones/:uuid',
          element: createElement(AnulacionDetalle),
        }),
        createElement(Route, {
          path: '/anulaciones',
          element: createElement('div', { 'data-testid': 'dest-list' }),
        }),
      ),
    ),
    { wrapper },
  );
}

describe('AnulacionDetalle', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('T1: renders the anulación data once loaded', async () => {
    mockedFetch.mockResolvedValue(baseAnulacion());
    renderDetalle();

    expect(await screen.findByTestId('anulacion-detalle-page')).toHaveTextContent('Placa duplicada');
    expect(screen.getAllByTestId('estado-anulacion-badge-iniciada').length).toBeGreaterThan(0);
  });

  it('T2: walks uuid_anulacion_padre backwards to build the chain', async () => {
    mockedFetch.mockImplementation(async (uuid: string) => {
      if (uuid === UUID) {
        return baseAnulacion({ uuid_anulacion_padre: PADRE_UUID, estado: 'autorizada' });
      }
      if (uuid === PADRE_UUID) {
        return baseAnulacion({ uuid: PADRE_UUID, uuid_anulacion_padre: null, estado: 'iniciada' });
      }
      throw new Error(`unexpected uuid ${uuid}`);
    });

    renderDetalle();

    await waitFor(() =>
      expect(screen.getByTestId(`workflow-chain-item-${PADRE_UUID}`)).toBeInTheDocument(),
    );
    expect(screen.getByTestId(`workflow-chain-item-${UUID}`)).toBeInTheDocument();
    expect(mockedFetch).toHaveBeenCalledWith(UUID);
    expect(mockedFetch).toHaveBeenCalledWith(PADRE_UUID);
  });

  it('T3: "Aprobar" opens the modal, submits, and patches the page without a reload', async () => {
    const user = userEvent.setup();
    mockedFetch.mockResolvedValue(baseAnulacion());
    mockedTransicionar.mockResolvedValue(
      baseAnulacion({ uuid: '66666666-6666-6666-6666-666666666666', estado: 'autorizada' }),
    );

    renderDetalle();

    await screen.findByTestId('anulacion-detalle-transicion-autorizada');
    await user.click(screen.getByTestId('anulacion-detalle-transicion-autorizada'));
    await user.type(
      await screen.findByTestId('transicion-anulacion-motivo'),
      'Motivo válido para aprobar.',
    );
    await user.click(screen.getByTestId('transicion-anulacion-submit'));

    await waitFor(() =>
      expect(mockedTransicionar).toHaveBeenCalledWith(UUID, 'autorizada', 'Motivo válido para aprobar.'),
    );
    await waitFor(() =>
      expect(screen.getByTestId('estado-anulacion-badge-autorizada')).toBeInTheDocument(),
    );
    expect(screen.queryByTestId('transicion-anulacion-modal')).not.toBeInTheDocument();
  });

  it('T4: a terminal (ejecutada) anulación shows no transition buttons', async () => {
    mockedFetch.mockResolvedValue(baseAnulacion({ estado: 'ejecutada' }));
    renderDetalle();

    expect(await screen.findByTestId('anulacion-detalle-terminal')).toBeInTheDocument();
    expect(screen.queryByTestId('anulacion-detalle-transicion-autorizada')).not.toBeInTheDocument();
  });
});
