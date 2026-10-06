/**
 * `AlertaDetalle.test.tsx` -- HU-F19.5 detail page integration tests.
 *
 *  - T1: renders the alert's data once `fetchAlerta` resolves.
 *  - T2: the "Descartar" action opens the modal, submits, and the page
 *    reflects the updated `estado` without a page reload (local patch
 *    via `useAlertaDetalle.setAlerta`).
 *  - T3: when the alert is already `resuelta`, "Descartar" is disabled.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createElement, type ReactNode } from 'react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { SWRConfig } from 'swr';
import type * as AlertasApiModule from '../api/alertasApi';

vi.mock('../api/alertasApi', async () => {
  const actual = await vi.importActual<typeof AlertasApiModule>('../api/alertasApi');
  return { ...actual, fetchAlerta: vi.fn(), descartarAlerta: vi.fn() };
});

import { descartarAlerta, fetchAlerta } from '../api/alertasApi';
import AlertaDetalle from './AlertaDetalle';

const mockedFetchAlerta = fetchAlerta as ReturnType<typeof vi.fn>;
const mockedDescartar = descartarAlerta as ReturnType<typeof vi.fn>;

const UUID = '11111111-1111-1111-1111-111111111111';

function baseAlerta(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    uuid: UUID,
    fecha_retencion_hasta: '2027-09-01',
    created_at: '2026-09-01T08:00:00',
    created_by: null,
    sync_status: null,
    sync_timestamp: null,
    sync_attempts: null,
    uuid_sucursal: '22222222-2222-2222-2222-222222222222',
    uuid_usuario: '33333333-3333-3333-3333-333333333333',
    uuid_arqueo: null,
    tipo_alerta: 'descuadre_critico',
    valor_diferencia_efectivo: '1500.00',
    valor_diferencia_datafono: '0.00',
    uuid_alerta_padre: null,
    timestamp_evento: '2026-09-01T08:00:00',
    vigente_desde: '2026-09-01T08:00:00',
    vigente_hasta: null,
    estado: 'abierta',
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
      { initialEntries: [`/alertas/${UUID}`] },
      createElement(
        Routes,
        null,
        createElement(Route, { path: '/alertas/:uuid', element: createElement(AlertaDetalle) }),
        createElement(Route, { path: '/alertas', element: createElement('div', { 'data-testid': 'dest-list' }) }),
      ),
    ),
    { wrapper },
  );
}

describe('AlertaDetalle', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('T1: renders the alert data once loaded', async () => {
    mockedFetchAlerta.mockResolvedValue(baseAlerta());
    renderDetalle();

    expect(await screen.findByTestId('alerta-detalle-page')).toHaveTextContent('descuadre_critico');
    // Renders twice by design: once in the "Datos" header badge, once
    // inside the (1-hop, this fixture has no uuid_alerta_padre)
    // WorkflowChain history for the same current row.
    expect(screen.getAllByTestId('estado-alerta-badge-abierta').length).toBeGreaterThan(0);
  });

  it('T2: descartar submits and patches the page without a reload', async () => {
    const user = userEvent.setup();
    mockedFetchAlerta.mockResolvedValue(baseAlerta());
    mockedDescartar.mockResolvedValue(baseAlerta({ estado: 'resuelta' }));

    renderDetalle();

    await screen.findByTestId('alerta-detalle-descartar-button');
    await user.click(screen.getByTestId('alerta-detalle-descartar-button'));
    await user.type(
      await screen.findByTestId('descartar-alerta-observaciones'),
      'Diferencia justificada con soporte físico.',
    );
    await user.click(screen.getByTestId('descartar-alerta-submit'));

    await waitFor(() => expect(mockedDescartar).toHaveBeenCalledWith(UUID, 'Diferencia justificada con soporte físico.'));
    await waitFor(() => expect(screen.getByTestId('estado-alerta-badge-resuelta')).toBeInTheDocument());
    expect(screen.queryByTestId('descartar-alerta-modal')).not.toBeInTheDocument();
  });

  it('T3: a resuelta alert disables the Descartar action', async () => {
    mockedFetchAlerta.mockResolvedValue(baseAlerta({ estado: 'resuelta' }));
    renderDetalle();

    expect(await screen.findByTestId('alerta-detalle-descartar-button')).toBeDisabled();
  });

  it('T4: a placa-agregada alert shows a readable type and its placa/acción/suscripción (no raw uuids)', async () => {
    mockedFetchAlerta.mockResolvedValue(
      baseAlerta({
        tipo_alerta: 'suscripcion_placa_agregada',
        datos_nuevos: {
          placa: 'ABC123',
          accion: 'agregada',
          uuid_subscripcion: 'aaaaaaaa-bbbb-cccc-dddd-0123456789ab',
          uuid_vehiculo: 'ffffffff-ffff-ffff-ffff-ffffffffffff',
          uuid_sucursal: '22222222-2222-2222-2222-222222222222',
          actor: '33333333-3333-3333-3333-333333333333',
        },
      }),
    );
    renderDetalle();

    expect(await screen.findByTestId('alerta-detalle-tipo')).toHaveTextContent('Placa agregada a suscripción');
    expect(screen.getByTestId('alerta-detalle-placa')).toHaveTextContent('ABC123');
    expect(screen.getByTestId('alerta-detalle-accion')).toHaveTextContent('Agregada');
    expect(screen.getByTestId('alerta-detalle-suscripcion')).toHaveTextContent('…456789ab');
    // The vehicle / actor uuids are never printed.
    const page = screen.getByTestId('alerta-detalle-page');
    expect(page).not.toHaveTextContent('ffffffff-ffff-ffff-ffff-ffffffffffff');
    expect(page).not.toHaveTextContent('aaaaaaaa-bbbb-cccc-dddd-0123456789ab');
  });

  it('T5: fe_emision_fallida and placa_quitada get readable labels; unknown types fall back to the raw code', async () => {
    mockedFetchAlerta.mockResolvedValue(baseAlerta({ tipo_alerta: 'fe_emision_fallida' }));
    const { unmount } = renderDetalle();
    expect(await screen.findByTestId('alerta-detalle-tipo')).toHaveTextContent(
      'Falló la emisión de factura electrónica',
    );
    // No datos_nuevos => no placa/acción rows.
    expect(screen.queryByTestId('alerta-detalle-placa')).not.toBeInTheDocument();
    unmount();

    mockedFetchAlerta.mockResolvedValue(baseAlerta({ tipo_alerta: 'suscripcion_placa_quitada' }));
    renderDetalle();
    expect(await screen.findByTestId('alerta-detalle-tipo')).toHaveTextContent('Placa quitada de suscripción');
  });

  it('T6 (PT-1): "Volver" returns to the previous inbox URL keeping its filters', async () => {
    const user = userEvent.setup();
    mockedFetchAlerta.mockResolvedValue(baseAlerta());
    render(
      createElement(
        MemoryRouter,
        { initialEntries: ['/alertas?estado=abierta&severidad=info', `/alertas/${UUID}`], initialIndex: 1 },
        createElement(
          Routes,
          null,
          createElement(Route, { path: '/alertas/:uuid', element: createElement(AlertaDetalle) }),
          createElement(Route, { path: '/alertas', element: createElement(SearchProbe) }),
        ),
      ),
      { wrapper },
    );

    await user.click(await screen.findByTestId('alerta-detalle-back'));
    expect(screen.getByTestId('search-probe')).toHaveTextContent('?estado=abierta&severidad=info');
  });
});

function SearchProbe(): JSX.Element {
  const location = useLocation();
  return createElement('div', { 'data-testid': 'search-probe' }, location.search);
}
