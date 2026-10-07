/**
 * H8 — "Volver" inside the subscription sale wizard, wired through the REAL
 * `<Venta />` inside `<SuscripcionesSheet />` (the sheet spec stubs Venta, so
 * it cannot catch a wrong `onCancel` wiring).
 *
 *   - mid-flow (step >= 2) "Volver" goes ONE step back and the sheet stays
 *     in venta mode (never the list).
 *   - only step 1 "Volver" lands on the list.
 *   - cupos (add/remove plates) "Volver" lands on the list it came from.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, fireEvent, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { defaultValue?: string }) => opts?.defaultValue ?? key,
  }),
}));
vi.mock('@parkos/ui-kit/hooks', () => ({
  useAuth: () => ({ sucursal: { uuid: 'suc-1' }, permisos: ['gestionar_placas_suscripcion'] }),
}));

const TIPO_CARRO = '00000000-0000-0000-0000-00000000aa02';
const PLAN_CARRO = '00000000-0000-0000-0000-0000000000a1';

vi.mock('../hooks/useVentaSuscripcion', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../hooks/useVentaSuscripcion')>();
  return {
    ...actual,
    useVentaSuscripcion: () => ({
      trigger: vi.fn(),
      isMutating: false,
      error: undefined,
      data: undefined,
    }),
  };
});
vi.mock('../hooks/useTiposSubscripciones', () => ({
  useTiposSubscripciones: () => ({
    data: [
      {
        uuid: PLAN_CARRO,
        tipo: 'MENSUAL_CARRO',
        uuid_tipo_vehiculo: TIPO_CARRO,
        valor: 30000,
        duracion_dias: 30,
        cantidad_maxima_vehiculos: 1,
        mismo_tipo_vehiculo: true,
        tipo_cliente_permitido: 'natural',
      },
    ],
    error: undefined,
    refresh: async () => undefined,
    isLoading: false,
  }),
}));
vi.mock('../../catalogos/hooks/useTiposVehiculo', () => ({
  useTiposVehiculo: () => ({
    tipos: [
      { uuid: TIPO_CARRO, tipo: 'carro', vigente_desde: '', vigente_hasta: null, estado: 'activo' },
    ],
    isLoading: false,
    error: undefined,
    refresh: async () => undefined,
    isFromFallback: false,
  }),
}));
vi.mock('../../facturacion/components/PagoModal', () => ({
  PagoModal: () => <div data-testid="pago-modal" />,
}));

vi.mock('../hooks/useSuscripcionesActivas', () => ({
  useSuscripcionesActivas: () => ({ data: [], error: undefined, refresh: vi.fn() }),
}));
vi.mock('../hooks/useSuscripcionesRenovables', () => ({
  useSuscripcionesRenovables: () => ({ data: [], error: undefined, refresh: vi.fn() }),
}));
vi.mock('./RenovarSuscripcionPanel', () => ({ RenovarSuscripcionPanel: () => null }));
vi.mock('../hooks/useBuscarSuscripcionPorIdentificacion', () => ({
  useBuscarSuscripcionPorIdentificacion: () => ({
    trigger: vi.fn(),
    isMutating: false,
    error: undefined,
    data: undefined,
  }),
}));
vi.mock('../hooks/useAgregarVehiculoSuscripcion', () => ({
  useAgregarVehiculoSuscripcion: () => ({
    trigger: vi.fn(),
    isMutating: false,
    error: undefined,
    data: undefined,
  }),
}));
vi.mock('../hooks/useQuitarVehiculoSuscripcion', () => ({
  useQuitarVehiculoSuscripcion: () => ({
    trigger: vi.fn(),
    isMutating: false,
    error: undefined,
    data: undefined,
  }),
}));

import { useDashboardDrawerStore } from '@/store/dashboardDrawerStore';
import { SuscripcionesSheet } from './SuscripcionesSheet';

// Each selection and its "Siguiente" click are separate act() calls (React 18 batching).
async function click(testId: string): Promise<void> {
  await act(async () => {
    fireEvent.click(screen.getByTestId(testId));
  });
}
async function change(testId: string, value: string): Promise<void> {
  await act(async () => {
    fireEvent.change(screen.getByTestId(testId), { target: { value } });
  });
}

async function abrirVenta(): Promise<void> {
  useDashboardDrawerStore.getState().open('suscripciones', 'sidebar-suscripciones');
  render(
    <MemoryRouter>
      <SuscripcionesSheet />
    </MemoryRouter>,
  );
  await click('suscripciones-sheet-nueva-venta');
}

async function hastaPlacas(): Promise<void> {
  await change('venta-cliente-numero', '900123456');
  await change('venta-cliente-nombre', 'ACME');
  await click('venta-paso-1-siguiente');
  await click(`venta-tipo-vehiculo-${TIPO_CARRO}`);
  await click('venta-paso-2-siguiente');
  await click(`venta-plan-${PLAN_CARRO}`);
  await click('venta-paso-3-siguiente');
  await change('venta-cantidad-input', '1');
  await click('venta-paso-4-siguiente');
  expect(screen.getByTestId('venta-paso-5')).toBeDefined();
}

beforeEach(() => {
  cleanup();
  useDashboardDrawerStore.getState().close();
});

describe('<SuscripcionesSheet /> + real <Venta /> — H8 "Volver"', () => {
  it('plate registration step: "Volver" goes to the quantity step, not the list', async () => {
    await abrirVenta();
    await hastaPlacas();

    await click('venta-volver');

    expect(screen.getByTestId('venta-paso-4')).toBeDefined();
    expect(screen.queryByTestId('suscripciones-buscar-form')).toBeNull();
  });

  it('walks back one step at a time and only step 1 lands on the list', async () => {
    await abrirVenta();
    await hastaPlacas();

    for (const paso of [4, 3, 2, 1]) {
      await click('venta-volver');
      expect(screen.getByTestId(`venta-paso-${paso}`)).toBeDefined();
      expect(screen.queryByTestId('suscripciones-buscar-form')).toBeNull();
    }

    await click('venta-volver');

    expect(screen.getByTestId('suscripciones-buscar-form')).toBeDefined();
    expect(screen.queryByTestId('venta-page')).toBeNull();
  });
});
