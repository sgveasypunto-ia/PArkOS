/**
 * PT-1 round trip: inbox (with filters) -> detail -> "Volver" lands on the
 * inbox with the SAME filters (they live in the querystring, "Volver" is
 * history back).
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createElement, type ReactNode } from 'react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { SWRConfig } from 'swr';

vi.mock('@parkos/ui-kit/hooks', () => ({
  useAdminAuth: () => ({ sucursalUuids: ['22222222-2222-2222-2222-222222222222'] }),
}));
vi.mock('@/features/sucursales/hooks/useSucursalesDirectorio', () => ({
  useSucursalesDirectorio: () => ({
    sucursales: [{ uuid: '22222222-2222-2222-2222-222222222222', nombre: 'Sede Norte' }],
  }),
}));
vi.mock('../api/alertasApi', () => ({
  fetchAlertas: vi.fn(),
  fetchAlerta: vi.fn(),
  descartarAlerta: vi.fn(),
}));

import { fetchAlerta, fetchAlertas } from '../api/alertasApi';
import AlertaDetalle from './AlertaDetalle';
import AlertasList from './AlertasList';

const UUID = '11111111-1111-1111-1111-111111111111';
const SUC = '22222222-2222-2222-2222-222222222222';

const ALERTA = {
  uuid: UUID,
  fecha_retencion_hasta: '2027-09-01',
  created_at: '2026-09-01T08:00:00',
  created_by: null,
  sync_status: null,
  sync_timestamp: null,
  sync_attempts: null,
  uuid_sucursal: SUC,
  uuid_usuario: null,
  uuid_arqueo: null,
  tipo_alerta: 'suscripcion_placa_agregada',
  valor_diferencia_efectivo: null,
  valor_diferencia_datafono: null,
  uuid_alerta_padre: null,
  timestamp_evento: '2026-09-01T08:00:00',
  vigente_desde: '2026-09-01T08:00:00',
  vigente_hasta: null,
  estado: 'abierta',
  severity: 'info',
  datos_nuevos: { placa: 'ABC123', accion: 'agregada' },
};

function wrapper({ children }: { children: ReactNode }): JSX.Element {
  return createElement(SWRConfig, { value: { provider: (): never => new Map() as never } }, children);
}

describe('Alertas: Volver keeps the inbox filters (PT-1)', () => {
  afterEach(() => vi.clearAllMocks());

  it('restores filters from the URL, lists the new types readably, and returns to them from the detail', async () => {
    (fetchAlertas as ReturnType<typeof vi.fn>).mockResolvedValue({ items: [ALERTA], next_cursor: null });
    (fetchAlerta as ReturnType<typeof vi.fn>).mockResolvedValue(ALERTA);
    const user = userEvent.setup();

    render(
      createElement(
        MemoryRouter,
        { initialEntries: ['/alertas?estado=abierta&severidad=info&tipo_alerta=suscripcion_placa_agregada'] },
        createElement(
          Routes,
          null,
          createElement(Route, { path: '/alertas', element: createElement(AlertasList) }),
          createElement(Route, { path: '/alertas/:uuid', element: createElement(AlertaDetalle) }),
        ),
      ),
      { wrapper },
    );

    // Filters seeded from the URL and sent to the API ("info", not "baja").
    expect(await screen.findByTestId(`alertas-row-${UUID}`)).toHaveTextContent('Placa agregada a suscripción');
    expect(screen.getByTestId('alertas-filters-estado')).toHaveValue('abierta');
    expect(screen.getByTestId('alertas-filters-severidad')).toHaveValue('info');
    expect(fetchAlertas).toHaveBeenCalledWith(
      expect.objectContaining({ estado: 'abierta', severidad: 'info' }),
    );

    await user.click(screen.getByTestId(`alertas-row-open-${UUID}`));
    expect(await screen.findByTestId('alerta-detalle-placa')).toHaveTextContent('ABC123');
    expect(screen.getByTestId('alerta-detalle-sucursal')).toHaveTextContent('Sede Norte');

    await user.click(screen.getByTestId('alerta-detalle-back'));

    // Back on the inbox with the same filters (not reset, not the dashboard).
    await waitFor(() => {
      expect(screen.getByTestId('alertas-page')).toBeInTheDocument();
    });
    expect(screen.getByTestId('alertas-filters-estado')).toHaveValue('abierta');
    expect(screen.getByTestId('alertas-filters-severidad')).toHaveValue('info');
    expect(screen.getByTestId('alertas-filters-tipo')).toHaveValue('suscripcion_placa_agregada');
  });

  it('writes a changed filter to the URL and ignores an unknown severity from a stale link', async () => {
    (fetchAlertas as ReturnType<typeof vi.fn>).mockResolvedValue({ items: [], next_cursor: null });
    const user = userEvent.setup();
    render(
      createElement(
        MemoryRouter,
        { initialEntries: ['/alertas?severidad=baja'] },
        createElement(Routes, null, createElement(Route, { path: '/alertas', element: createElement(AlertasList) })),
      ),
      { wrapper },
    );

    // `baja` is not a backend severity (critical|warning|info): it is dropped.
    await waitFor(() => expect(screen.getByTestId('alertas-filters-severidad')).toHaveValue(''));
    await user.selectOptions(screen.getByTestId('alertas-filters-severidad'), 'info');
    await waitFor(() => {
      expect(fetchAlertas).toHaveBeenCalledWith(expect.objectContaining({ severidad: 'info' }));
    });
    const options = Array.from(
      (screen.getByTestId('alertas-filters-severidad') as HTMLSelectElement).options,
    ).map((o) => o.value);
    expect(options).toEqual(['', 'critical', 'warning', 'info']);
  });
});
