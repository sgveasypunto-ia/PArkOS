/**
 * `ReclamoDetalle.test.tsx` -- HU-F20.3 detail page integration tests.
 * Mirrors `AnulacionDetalle.test.tsx`.
 *
 *  - T1: renders the reclamo's data once `fetchReclamo` resolves.
 *  - T2: walks `uuid_reclamo_padre` backwards to build the chain.
 *  - T3: the "Tomar en revisión" action opens the modal, submits, and
 *    the page reflects the updated `estado` without a page reload.
 *  - T4: a terminal (`resuelto`) reclamo shows no transition buttons.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createElement, type ReactNode } from 'react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { SWRConfig } from 'swr';
import type * as ReclamosApiModule from '../api/reclamosApi';

vi.mock('../api/reclamosApi', async () => {
  const actual = await vi.importActual<typeof ReclamosApiModule>('../api/reclamosApi');
  return { ...actual, fetchReclamo: vi.fn(), transicionarReclamo: vi.fn() };
});

import { fetchReclamo, transicionarReclamo } from '../api/reclamosApi';
import ReclamoDetalle from './ReclamoDetalle';

const mockedFetch = fetchReclamo as ReturnType<typeof vi.fn>;
const mockedTransicionar = transicionarReclamo as ReturnType<typeof vi.fn>;

const UUID = '11111111-1111-1111-1111-111111111111';
const PADRE_UUID = '55555555-5555-5555-5555-555555555555';

function baseReclamo(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    uuid: UUID,
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

function renderDetalle() {
  return render(
    createElement(
      MemoryRouter,
      { initialEntries: [`/reclamos/${UUID}`] },
      createElement(
        Routes,
        null,
        createElement(Route, { path: '/reclamos/:uuid', element: createElement(ReclamoDetalle) }),
        createElement(Route, {
          path: '/reclamos',
          element: createElement('div', { 'data-testid': 'dest-list' }),
        }),
      ),
    ),
    { wrapper },
  );
}

describe('ReclamoDetalle', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('T1: renders the reclamo data once loaded', async () => {
    mockedFetch.mockResolvedValue(baseReclamo());
    renderDetalle();

    expect(await screen.findByTestId('reclamo-detalle-page')).toHaveTextContent('Cobro duplicado');
    expect(screen.getAllByTestId('estado-reclamo-badge-recibido').length).toBeGreaterThan(0);
  });

  it('T2: walks uuid_reclamo_padre backwards to build the chain', async () => {
    mockedFetch.mockImplementation(async (uuid: string) => {
      if (uuid === UUID) {
        return baseReclamo({ uuid_reclamo_padre: PADRE_UUID, estado: 'en_investigacion' });
      }
      if (uuid === PADRE_UUID) {
        return baseReclamo({ uuid: PADRE_UUID, uuid_reclamo_padre: null, estado: 'recibido' });
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

  it('T3: "Tomar en revisión" opens the modal, submits, and patches the page', async () => {
    const user = userEvent.setup();
    mockedFetch.mockResolvedValue(baseReclamo());
    mockedTransicionar.mockResolvedValue(
      baseReclamo({ uuid: '66666666-6666-6666-6666-666666666666', estado: 'en_investigacion' }),
    );

    renderDetalle();

    await screen.findByTestId('reclamo-detalle-transicion-en_investigacion');
    await user.click(screen.getByTestId('reclamo-detalle-transicion-en_investigacion'));
    await user.type(
      await screen.findByTestId('transicion-reclamo-motivo'),
      'Motivo válido para investigar.',
    );
    await user.click(screen.getByTestId('transicion-reclamo-submit'));

    await waitFor(() =>
      expect(mockedTransicionar).toHaveBeenCalledWith(
        UUID,
        'en_investigacion',
        'Motivo válido para investigar.',
      ),
    );
    await waitFor(() =>
      expect(screen.getByTestId('estado-reclamo-badge-en_investigacion')).toBeInTheDocument(),
    );
    expect(screen.queryByTestId('transicion-reclamo-modal')).not.toBeInTheDocument();
  });

  it('T4: a terminal (resuelto) reclamo shows no transition buttons', async () => {
    mockedFetch.mockResolvedValue(baseReclamo({ estado: 'resuelto' }));
    renderDetalle();

    expect(await screen.findByTestId('reclamo-detalle-terminal')).toBeInTheDocument();
    expect(screen.queryByTestId('reclamo-detalle-transicion-en_investigacion')).not.toBeInTheDocument();
  });
});
