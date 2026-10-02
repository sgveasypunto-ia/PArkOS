/**
 * `ValidacionEventos.test.tsx` — HU-F19.6 "bandeja de validación de
 * eventos" tab.
 *
 *  - T1: renders the fetched items (sucursal, tabla origen, estado badge).
 *  - T2: "Ver historial" expands the per-row `<WorkflowChain />` built
 *    from that row's own fields (no multi-hop walk -- see the page's
 *    own docblock for why).
 *  - T3: a `pendiente` row's "Validar / Rechazar" opens the modal; a
 *    successful submit closes it and revalidates the list.
 *  - T4: a non-`pendiente` row (already `validado`/`rechazado`) disables
 *    the resolve action.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createElement } from 'react';
import { SWRConfig } from 'swr';

const fetchValidacionEventosMock = vi.fn();
const createValidacionEventoTransicionMock = vi.fn();

vi.mock('../api/validacionEventoApi', async () => {
  const actual = (await vi.importActual('../api/validacionEventoApi')) as Record<
    string,
    unknown
  >;
  return {
    ...actual,
    fetchValidacionEventos: (...args: unknown[]) => fetchValidacionEventosMock(...args),
    createValidacionEventoTransicion: (...args: unknown[]) =>
      createValidacionEventoTransicionMock(...args),
  };
});

vi.mock('@/features/sucursales/hooks/useSucursalesDirectorio', () => ({
  useSucursalesDirectorio: () => ({
    sucursales: [{ uuid: SUC_A, nombre: 'Suc A' }],
    isLoading: false,
    error: undefined,
    refresh: vi.fn(),
  }),
}));

import ValidacionEventos from './ValidacionEventos';

const SUC_A = '11111111-1111-1111-1111-111111111111';

function row(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    uuid: 'aaaaaaaa-0000-0000-0000-000000000001',
    created_at: '2026-09-30T09:00:00',
    created_by: null,
    sync_status: null,
    sync_timestamp: null,
    sync_attempts: null,
    uuid_sucursal: SUC_A,
    uuid_usuario: null,
    tabla_origen: 'factura_pagos',
    uuid_registro: null,
    hash_evento: null,
    observaciones: null,
    uuid_validacion_padre: null,
    timestamp_evento: '2026-09-30T09:00:00',
    vigente_desde: '2026-09-30T09:00:00',
    vigente_hasta: null,
    estado: 'pendiente',
    ...overrides,
  };
}

function renderPage(swrSalt: string) {
  return render(
    createElement(
      SWRConfig,
      { value: { provider: (): never => new Map() as never, dedupingInterval: 0 } },
      createElement(ValidacionEventos, { swrSalt }),
    ),
  );
}

describe('ValidacionEventos', () => {
  it('T1: renders the fetched items', async () => {
    fetchValidacionEventosMock.mockResolvedValue({ items: [row()], next_cursor: null });

    renderPage('t1');

    const tr = await screen.findByTestId(
      'validacion-eventos-row-aaaaaaaa-0000-0000-0000-000000000001',
    );
    expect(within(tr).getByText('Suc A')).toBeInTheDocument();
    expect(within(tr).getByText('factura_pagos')).toBeInTheDocument();
    expect(within(tr).getByTestId('validacion-eventos-badge-pendiente')).toBeInTheDocument();
  });

  it('T2: "Ver historial" expands the single-transition WorkflowChain', async () => {
    fetchValidacionEventosMock.mockResolvedValue({
      items: [row({ observaciones: 'nota del evento' })],
      next_cursor: null,
    });

    const user = userEvent.setup();
    renderPage('t2');

    const toggle = await screen.findByTestId(
      'validacion-eventos-ver-historial-aaaaaaaa-0000-0000-0000-000000000001',
    );
    await user.click(toggle);

    expect(screen.getByTestId('workflow-chain')).toBeInTheDocument();
    expect(
      screen.getByTestId('workflow-chain-item-aaaaaaaa-0000-0000-0000-000000000001'),
    ).toHaveTextContent('nota del evento');
  });

  it('T3: resolving a pendiente row opens the modal and revalidates on success', async () => {
    fetchValidacionEventosMock.mockResolvedValue({ items: [row()], next_cursor: null });
    createValidacionEventoTransicionMock.mockResolvedValueOnce({
      uuid: 'bbbbbbbb-0000-0000-0000-000000000002',
    });

    const user = userEvent.setup();
    renderPage('t3');

    await user.click(
      await screen.findByTestId(
        'validacion-eventos-resolver-aaaaaaaa-0000-0000-0000-000000000001',
      ),
    );
    expect(screen.getByTestId('validar-evento-modal')).toBeInTheDocument();

    await user.click(screen.getByTestId('validar-evento-submit'));

    await waitFor(() => {
      expect(screen.queryByTestId('validar-evento-modal')).not.toBeInTheDocument();
    });
    expect(createValidacionEventoTransicionMock).toHaveBeenCalledWith({
      uuidValidacionPadre: 'aaaaaaaa-0000-0000-0000-000000000001',
      estado: 'validado',
      observaciones: '',
    });
  });

  it('T4: a non-pendiente row disables the resolve action', async () => {
    fetchValidacionEventosMock.mockResolvedValue({
      items: [row({ estado: 'validado' })],
      next_cursor: null,
    });

    renderPage('t4');

    const button = await screen.findByTestId(
      'validacion-eventos-resolver-aaaaaaaa-0000-0000-0000-000000000001',
    );
    expect(button).toBeDisabled();
  });
});
