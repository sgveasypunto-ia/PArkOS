/**
 * PT-1: "Volver" in the reclamo / anulación detail returns to the previous
 * screen (history back), falling back to the list when there is no in-app
 * history (deep link).
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createElement, type ReactNode } from 'react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { SWRConfig } from 'swr';
import type * as ReclamosApiModule from '../api/reclamosApi';
import type * as AnulacionesApiModule from '../api/anulacionesApi';

vi.mock('../api/reclamosApi', async () => {
  const actual = await vi.importActual<typeof ReclamosApiModule>('../api/reclamosApi');
  return { ...actual, fetchReclamo: vi.fn(), transicionarReclamo: vi.fn() };
});
vi.mock('../api/anulacionesApi', async () => {
  const actual = await vi.importActual<typeof AnulacionesApiModule>('../api/anulacionesApi');
  return { ...actual, fetchAnulacion: vi.fn(), transicionarAnulacion: vi.fn() };
});

import { fetchAnulacion } from '../api/anulacionesApi';
import { fetchReclamo } from '../api/reclamosApi';
import AnulacionDetalle from './AnulacionDetalle';
import ReclamoDetalle from './ReclamoDetalle';

const UUID = '11111111-1111-1111-1111-111111111111';

const RECLAMO = {
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
};

function wrapper({ children }: { children: ReactNode }): JSX.Element {
  return createElement(SWRConfig, { value: { provider: (): never => new Map() as never } }, children);
}

function Probe(): JSX.Element {
  const location = useLocation();
  return createElement('div', { 'data-testid': 'list-probe' }, location.pathname + location.search);
}

function renderAt(entries: string[], index: number, detail: JSX.Element, base: 'reclamos' | 'anulaciones') {
  return render(
    createElement(
      MemoryRouter,
      { initialEntries: entries, initialIndex: index },
      createElement(
        Routes,
        null,
        createElement(Route, { path: `/${base}/:uuid`, element: detail }),
        createElement(Route, { path: `/${base}`, element: createElement(Probe) }),
        createElement(Route, { path: '/otra-pantalla', element: createElement(Probe) }),
      ),
    ),
    { wrapper },
  );
}

describe('Volver en detalles de workflows (PT-1)', () => {
  afterEach(() => vi.clearAllMocks());

  it('ReclamoDetalle: goes back to the screen it came from (not always the list)', async () => {
    (fetchReclamo as ReturnType<typeof vi.fn>).mockResolvedValue(RECLAMO);
    renderAt(['/otra-pantalla?x=1', `/reclamos/${UUID}`], 1, createElement(ReclamoDetalle), 'reclamos');

    await userEvent.click(await screen.findByTestId('reclamo-detalle-back'));
    expect(screen.getByTestId('list-probe')).toHaveTextContent('/otra-pantalla?x=1');
  });

  it('ReclamoDetalle: falls back to the list on a deep link', async () => {
    (fetchReclamo as ReturnType<typeof vi.fn>).mockResolvedValue(RECLAMO);
    renderAt([`/reclamos/${UUID}`], 0, createElement(ReclamoDetalle), 'reclamos');

    await userEvent.click(await screen.findByTestId('reclamo-detalle-back'));
    expect(screen.getByTestId('list-probe')).toHaveTextContent('/reclamos');
  });

  it('AnulacionDetalle: goes back to the previous screen and falls back to the list on a deep link', async () => {
    (fetchAnulacion as ReturnType<typeof vi.fn>).mockResolvedValue({
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
    });
    const first = renderAt(
      ['/otra-pantalla?y=2', `/anulaciones/${UUID}`],
      1,
      createElement(AnulacionDetalle),
      'anulaciones',
    );
    await userEvent.click(await screen.findByTestId('anulacion-detalle-back'));
    expect(screen.getByTestId('list-probe')).toHaveTextContent('/otra-pantalla?y=2');
    first.unmount();

    renderAt([`/anulaciones/${UUID}`], 0, createElement(AnulacionDetalle), 'anulaciones');
    await userEvent.click(await screen.findByTestId('anulacion-detalle-back'));
    expect(screen.getByTestId('list-probe')).toHaveTextContent('/anulaciones');
  });
});
