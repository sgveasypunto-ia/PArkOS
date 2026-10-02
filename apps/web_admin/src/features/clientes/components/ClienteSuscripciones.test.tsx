/**
 * `ClienteSuscripciones.test.tsx` — vigentes/históricas split + the
 * "vence en N días" badge (HU-F20.1), mocked at the `clientesApi.ts`
 * boundary.
 */
import { createElement } from 'react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

import { SucursalProvider } from '@/lib/sucursal-context';

function wrapper({ children }: { children: ReactNode }): JSX.Element {
  return createElement(SucursalProvider, null, children);
}

const { UUID_CLIENTE, UUID_SUBSCRIPCION, VIGENTE } = vi.hoisted(() => {
  const UUID_CLIENTE = '11111111-1111-1111-1111-111111111111';
  const UUID_SUBSCRIPCION = '22222222-2222-2222-2222-222222222222';
  return {
    UUID_CLIENTE,
    UUID_SUBSCRIPCION,
    VIGENTE: {
      uuid: UUID_SUBSCRIPCION,
      uuid_cliente: UUID_CLIENTE,
      uuid_sucursal: 'suc-1',
      uuid_tipo_subscripcion: 'plan-1',
      fecha_inicio_cobertura: '2026-01-01',
      fecha_vencimiento: '2026-12-31',
      dias_alerta_pre_vencimiento: 7,
      vigente_desde: '2026-01-01T00:00:00',
      vigente_hasta: null,
      estado: 'activo',
      created_at: '2026-01-01T00:00:00',
      created_by: null,
      sync_status: null,
    },
  };
});

vi.mock('../api/clientesApi', () => ({
  listSubscripcionesClienteByCliente: vi.fn().mockResolvedValue([VIGENTE]),
  getSubscripcionClienteHistory: vi.fn().mockResolvedValue([VIGENTE]),
  // HU-F20.2 -- ClienteSuscripciones.tsx now imports these for the
  // nueva/editar flow; stubbed (unused by these 2 render-only tests
  // since the Dialog stays closed, but required so the named import
  // bindings exist).
  createSubscripcionCliente: vi.fn(),
  updateSubscripcionCliente: vi.fn(),
  createSubscripcionVehiculo: vi.fn(),
  listVehiculos: vi.fn().mockResolvedValue({ items: [], next_cursor: null }),
}));

vi.mock('@/features/catalogos/api/catalogApi', () => ({
  listCatalog: vi.fn().mockResolvedValue([]),
}));

import { ClienteSuscripciones } from './ClienteSuscripciones';

describe('<ClienteSuscripciones />', () => {
  it('renders the vigente subscripcion with its vence-en badge', async () => {
    render(<ClienteSuscripciones uuidCliente={UUID_CLIENTE} />, { wrapper });

    await waitFor(() => {
      expect(
        screen.getByTestId(`cliente-suscripcion-vigente-${UUID_SUBSCRIPCION}`),
      ).toBeInTheDocument();
    });
    expect(screen.getByTestId(`cliente-suscripcion-dias-${UUID_SUBSCRIPCION}`)).toBeInTheDocument();
  });

  it('renders the historicas section from the /history call', async () => {
    render(<ClienteSuscripciones uuidCliente={UUID_CLIENTE} />, { wrapper });

    await waitFor(() => {
      expect(
        screen.getByTestId(`cliente-suscripcion-historica-${UUID_SUBSCRIPCION}`),
      ).toBeInTheDocument();
    });
  });

  it('opens the SuscripcionForm dialog in create mode via "Nueva suscripción"', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    render(<ClienteSuscripciones uuidCliente={UUID_CLIENTE} />, { wrapper });

    await waitFor(() => {
      expect(screen.getByTestId('cliente-suscripcion-nueva')).toBeInTheDocument();
    });
    await userEvent.click(screen.getByTestId('cliente-suscripcion-nueva'));

    expect(screen.getByTestId('suscripcion-form-dialog')).toBeInTheDocument();
    expect(screen.getByTestId('suscripcion-form')).toBeInTheDocument();
  });

  it('opens the SuscripcionForm dialog in edit mode via "Editar"', async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    render(<ClienteSuscripciones uuidCliente={UUID_CLIENTE} />, { wrapper });

    await waitFor(() => {
      expect(
        screen.getByTestId(`cliente-suscripcion-editar-${UUID_SUBSCRIPCION}`),
      ).toBeInTheDocument();
    });
    await userEvent.click(screen.getByTestId(`cliente-suscripcion-editar-${UUID_SUBSCRIPCION}`));

    expect(screen.getByTestId('suscripcion-form-dialog')).toBeInTheDocument();
    expect(
      (screen.getByTestId('suscripcion-field-dias-alerta') as HTMLInputElement).value,
    ).toBe(String(VIGENTE.dias_alerta_pre_vencimiento ?? 7));
  });
});
