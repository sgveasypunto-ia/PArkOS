/**
 * `ClienteSuscripciones.test.tsx` — vigentes/históricas split + the
 * "vence en N días" badge (HU-F20.1), and the PT-3 renewal action
 * ("Renovar" only when the server says `puede_renovar`), mocked at the
 * `clientesApi.ts` boundary.
 */
import { createElement } from 'react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SWRConfig } from 'swr';
import type * as ClientesApiModule from '../api/clientesApi';

import { SucursalProvider } from '@/lib/sucursal-context';

function wrapper({ children }: { children: ReactNode }): JSX.Element {
  return createElement(
    SWRConfig,
    { value: { provider: (): never => new Map() as never } },
    createElement(SucursalProvider, null, children),
  );
}

const { UUID_CLIENTE, UUID_SUBSCRIPCION, VIGENTE, HISTORICA } = vi.hoisted(() => {
  const UUID_CLIENTE = '11111111-1111-1111-1111-111111111111';
  const UUID_SUBSCRIPCION = '22222222-2222-2222-2222-222222222222';
  const VIGENTE = {
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
    dias_restantes: 200,
    puede_renovar: false,
  };
  return {
    UUID_CLIENTE,
    UUID_SUBSCRIPCION,
    VIGENTE,
    HISTORICA: {
      ...VIGENTE,
      uuid: '99999999-9999-9999-9999-999999999999',
      vigente_hasta: '2026-06-01T00:00:00',
      estado: 'inactivo',
    },
  };
});

const mockList = vi.fn();
const mockHistory = vi.fn();
const mockRenovar = vi.fn();

vi.mock('../api/clientesApi', async () => {
  const actual = await vi.importActual<typeof ClientesApiModule>('../api/clientesApi');
  return {
    ...actual,
    listSubscripcionesClienteByCliente: (...a: unknown[]) => mockList(...a),
    getSubscripcionClienteHistory: (...a: unknown[]) => mockHistory(...a),
    renovarSubscripcion: (...a: unknown[]) => mockRenovar(...a),
    createSubscripcionCliente: vi.fn(),
    updateSubscripcionCliente: vi.fn(),
    createSubscripcionVehiculo: vi.fn(),
    listVehiculos: vi.fn().mockResolvedValue({ items: [], next_cursor: null }),
  };
});

vi.mock('@/features/catalogos/api/catalogApi', () => ({
  listCatalog: vi.fn().mockResolvedValue([]),
}));

import { ClientesApiError } from '../api/clientesApi';
import { soloHistoricas } from '../lib/historicas';
import { ClienteSuscripciones } from './ClienteSuscripciones';

const RENOVABLE = { ...VIGENTE, fecha_vencimiento: '2026-01-05', dias_restantes: 4, puede_renovar: true };

beforeEach(() => {
  mockList.mockReset().mockResolvedValue([VIGENTE]);
  // `/history` of a vigente's uuid returns that same OPEN row (the bug) --
  // plus, here, one closed version.
  mockHistory.mockReset().mockResolvedValue([VIGENTE, HISTORICA]);
  mockRenovar.mockReset();
});

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

  it('renders only CLOSED versions under Históricas and never repeats the vigente one', async () => {
    render(<ClienteSuscripciones uuidCliente={UUID_CLIENTE} />, { wrapper });

    await waitFor(() => {
      expect(screen.getByTestId(`cliente-suscripcion-historica-${HISTORICA.uuid}`)).toBeInTheDocument();
    });
    expect(
      screen.queryByTestId(`cliente-suscripcion-historica-${UUID_SUBSCRIPCION}`),
    ).not.toBeInTheDocument();
    // Still exactly once in Vigentes.
    expect(screen.getAllByTestId(`cliente-suscripcion-vigente-${UUID_SUBSCRIPCION}`)).toHaveLength(1);
  });

  it('shows the empty Históricas state when /history only returns the open row', async () => {
    mockHistory.mockResolvedValue([VIGENTE]);
    render(<ClienteSuscripciones uuidCliente={UUID_CLIENTE} />, { wrapper });

    await waitFor(() => {
      expect(screen.getByTestId('cliente-suscripciones-historicas-empty')).toBeInTheDocument();
    });
  });

  it('opens the SuscripcionForm dialog in create mode via "Nueva suscripción"', async () => {
    render(<ClienteSuscripciones uuidCliente={UUID_CLIENTE} />, { wrapper });

    await waitFor(() => {
      expect(screen.getByTestId('cliente-suscripcion-nueva')).toBeInTheDocument();
    });
    await userEvent.click(screen.getByTestId('cliente-suscripcion-nueva'));

    expect(screen.getByTestId('suscripcion-form-dialog')).toBeInTheDocument();
    expect(screen.getByTestId('suscripcion-form')).toBeInTheDocument();
  });

  it('opens the SuscripcionForm dialog in edit mode via "Editar"', async () => {
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

describe('<ClienteSuscripciones /> -- renovación (PT-3)', () => {
  it('does NOT show "Renovar" when puede_renovar is false (> 10 days left)', async () => {
    render(<ClienteSuscripciones uuidCliente={UUID_CLIENTE} />, { wrapper });
    await waitFor(() => {
      expect(
        screen.getByTestId(`cliente-suscripcion-vigente-${UUID_SUBSCRIPCION}`),
      ).toBeInTheDocument();
    });
    expect(
      screen.queryByTestId(`cliente-suscripcion-renovar-${UUID_SUBSCRIPCION}`),
    ).not.toBeInTheDocument();
  });

  it('does NOT recompute the window from dates: puede_renovar absent => no button', async () => {
    const { puede_renovar: _omit, ...sinFlag } = RENOVABLE;
    void _omit;
    mockList.mockResolvedValue([sinFlag]);
    render(<ClienteSuscripciones uuidCliente={UUID_CLIENTE} />, { wrapper });
    await waitFor(() => {
      expect(
        screen.getByTestId(`cliente-suscripcion-vigente-${UUID_SUBSCRIPCION}`),
      ).toBeInTheDocument();
    });
    expect(
      screen.queryByTestId(`cliente-suscripcion-renovar-${UUID_SUBSCRIPCION}`),
    ).not.toBeInTheDocument();
  });

  it('shows "Renovar" when puede_renovar is true, renews without asking for plates and refreshes the list', async () => {
    mockList.mockResolvedValue([RENOVABLE]);
    mockRenovar.mockResolvedValue({
      uuid_subscripcion_anterior: UUID_SUBSCRIPCION,
      uuid_subscripcion: '88888888-8888-8888-8888-888888888888',
      uuid_vehiculos: [],
      placas: ['ABC123'],
      fecha_inicio_cobertura: '2026-01-06',
      fecha_vencimiento: '2026-02-04',
      total_con_iva: 35700,
      factura_electronica_error: null,
    });
    render(<ClienteSuscripciones uuidCliente={UUID_CLIENTE} />, { wrapper });

    const btn = await screen.findByTestId(`cliente-suscripcion-renovar-${UUID_SUBSCRIPCION}`);
    const callsBefore = mockList.mock.calls.length;
    await userEvent.click(btn);

    const dialog = screen.getByTestId('renovar-dialog');
    expect(dialog).toBeInTheDocument();
    // No plate/vehicle inputs in the renewal flow.
    expect(screen.queryByTestId('suscripcion-agregar-vehiculo')).not.toBeInTheDocument();
    expect(screen.queryByTestId('renovar-referencia')).not.toBeInTheDocument(); // efectivo

    await userEvent.click(screen.getByTestId('renovar-confirmar'));

    await waitFor(() => {
      expect(screen.getByTestId('renovar-resultado')).toBeInTheDocument();
    });
    expect(mockRenovar).toHaveBeenCalledTimes(1);
    const [uuid, body, key] = mockRenovar.mock.calls[0] as [string, Record<string, unknown>, string];
    expect(uuid).toBe(UUID_SUBSCRIPCION);
    expect(body).toMatchObject({ medio_pago: 'efectivo' });
    expect(typeof key).toBe('string');
    expect(key.length).toBeGreaterThan(8);
    // List refreshed after the renewal.
    await waitFor(() => {
      expect(mockList.mock.calls.length).toBeGreaterThan(callsBefore);
    });
  });

  it('requires the voucher reference for datáfono and sends it', async () => {
    mockList.mockResolvedValue([RENOVABLE]);
    mockRenovar.mockResolvedValue({
      uuid_subscripcion_anterior: UUID_SUBSCRIPCION,
      uuid_subscripcion: '88888888-8888-8888-8888-888888888888',
      uuid_vehiculos: [],
      placas: [],
    });
    render(<ClienteSuscripciones uuidCliente={UUID_CLIENTE} />, { wrapper });

    await userEvent.click(await screen.findByTestId(`cliente-suscripcion-renovar-${UUID_SUBSCRIPCION}`));
    await userEvent.selectOptions(screen.getByTestId('renovar-medio-pago'), 'datafono');
    await userEvent.click(screen.getByTestId('renovar-confirmar'));

    expect(await screen.findByTestId('renovar-error')).toHaveTextContent(/voucher/i);
    expect(mockRenovar).not.toHaveBeenCalled();

    await userEvent.type(screen.getByTestId('renovar-referencia'), 'V-12345');
    await userEvent.click(screen.getByTestId('renovar-confirmar'));
    await waitFor(() => {
      expect(mockRenovar).toHaveBeenCalledTimes(1);
    });
    expect(mockRenovar.mock.calls[0]?.[1]).toMatchObject({
      medio_pago: 'datafono',
      referencia: 'V-12345',
    });
  });

  it('maps renovacion_fuera_de_ventana (409) to a readable message and keeps the dialog open', async () => {
    mockList.mockResolvedValue([RENOVABLE]);
    const body = JSON.stringify({
      detail: { error: 'renovacion_fuera_de_ventana', dias_restantes: 25, ventana_dias: 10 },
    });
    mockRenovar.mockRejectedValue(new ClientesApiError(`clientesApi: POST x -> 409: ${body}`, 409, body));
    render(<ClienteSuscripciones uuidCliente={UUID_CLIENTE} />, { wrapper });

    await userEvent.click(await screen.findByTestId(`cliente-suscripcion-renovar-${UUID_SUBSCRIPCION}`));
    await userEvent.click(screen.getByTestId('renovar-confirmar'));

    const err = await screen.findByTestId('renovar-error');
    expect(err.textContent).toMatch(/25 días/);
    expect(err.textContent).toMatch(/10 días o menos/);
    expect(screen.getByTestId('renovar-dialog')).toBeInTheDocument();
  });

  it('after an ambiguous failure (network) keeps the SAME Idempotency-Key and locks the payment data so a retry cannot double-charge', async () => {
    mockList.mockResolvedValue([RENOVABLE]);
    mockRenovar.mockRejectedValue(new Error('network'));
    render(<ClienteSuscripciones uuidCliente={UUID_CLIENTE} />, { wrapper });

    await userEvent.click(await screen.findByTestId(`cliente-suscripcion-renovar-${UUID_SUBSCRIPCION}`));
    await userEvent.click(screen.getByTestId('renovar-confirmar'));
    await screen.findByTestId('renovar-error');
    expect(screen.getByTestId('renovar-ambiguo')).toBeInTheDocument();
    expect(screen.getByTestId('renovar-medio-pago')).toBeDisabled();

    await userEvent.click(screen.getByTestId('renovar-confirmar'));
    await waitFor(() => {
      expect(mockRenovar).toHaveBeenCalledTimes(2);
    });
    expect(mockRenovar.mock.calls[0]?.[2]).toBe(mockRenovar.mock.calls[1]?.[2]);
    expect(mockRenovar.mock.calls[0]?.[1]).toEqual(mockRenovar.mock.calls[1]?.[1]);
  });

  it('after a definitive 4xx the payment data can be corrected and a NEW Idempotency-Key is used', async () => {
    mockList.mockResolvedValue([RENOVABLE]);
    const body = JSON.stringify({ detail: { error: 'voucher_requerido' } });
    mockRenovar.mockRejectedValue(new ClientesApiError(`clientesApi: POST x -> 400: ${body}`, 400, body));
    render(<ClienteSuscripciones uuidCliente={UUID_CLIENTE} />, { wrapper });

    await userEvent.click(await screen.findByTestId(`cliente-suscripcion-renovar-${UUID_SUBSCRIPCION}`));
    await userEvent.click(screen.getByTestId('renovar-confirmar'));
    await screen.findByTestId('renovar-error');
    expect(screen.queryByTestId('renovar-ambiguo')).not.toBeInTheDocument();
    const k1 = mockRenovar.mock.calls[0]?.[2];

    await userEvent.selectOptions(screen.getByTestId('renovar-medio-pago'), 'tarjeta');
    await userEvent.click(screen.getByTestId('renovar-confirmar'));
    await waitFor(() => {
      expect(mockRenovar).toHaveBeenCalledTimes(2);
    });
    expect(mockRenovar.mock.calls[1]?.[2]).not.toBe(k1);
  });

  it('refreshes the list when the dialog is closed', async () => {
    mockList.mockResolvedValue([RENOVABLE]);
    render(<ClienteSuscripciones uuidCliente={UUID_CLIENTE} />, { wrapper });
    await userEvent.click(await screen.findByTestId(`cliente-suscripcion-renovar-${UUID_SUBSCRIPCION}`));
    const before = mockList.mock.calls.length;
    await userEvent.click(screen.getByText('Cancelar'));
    await waitFor(() => {
      expect(mockList.mock.calls.length).toBeGreaterThan(before);
    });
  });
});

describe('soloHistoricas', () => {
  it('drops the vigentes, open/active rows and duplicates; keeps closed versions', () => {
    const out = soloHistoricas([VIGENTE, HISTORICA, HISTORICA], [VIGENTE]);
    expect(out.map((s) => s.uuid)).toEqual([HISTORICA.uuid]);
  });

  it('drops an open active row even if it is not in the vigentes list', () => {
    const otro = { ...VIGENTE, uuid: 'otro' };
    expect(soloHistoricas([otro], [])).toEqual([]);
  });
});
