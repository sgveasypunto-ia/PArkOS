/**
 * D2 — real-flow regression for the mensualidad exit.
 *
 * The earlier H5/H7 tests mocked `useCotizacion` (and the modal), so
 * they never exercised the real SWR cache. In the real app, confirming
 * the salida made `<SalidaPanel />` clear the `/cotizar` cache entry
 * BEFORE its "confirmada" state committed: the panel rendered a frame
 * with no cotizacion, `<SalidaMensualidad />` unmounted, the pending
 * factura state was lost and the drawer never closed.
 *
 * Here only the network boundary is mocked (`parkosFetch`, the salida
 * and factura mutations); `useCotizacion` + SWR + `<SalidaPanel />` +
 * `<SalidaMensualidad />` + `<CotizacionPanel />` are real.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor, cleanup } from '@testing-library/react';
import { SWRConfig, useSWRConfig } from 'swr';

import type * as UiKitFetchModule from '@parkos/ui-kit/fetch';

const UUID_INGRESO = '11111111-1111-4111-8111-111111111111';
const UUID_TARIFA = '22222222-2222-4222-8222-222222222222';
const UUID_SUBS = '33333333-3333-4333-8333-333333333333';

let ingresoCerrado = false;
const cotizarCalls: string[] = [];

vi.mock('@parkos/ui-kit/fetch', async (importOriginal) => {
  const actual = await importOriginal<typeof UiKitFetchModule>();
  return {
    ...actual,
    parkosFetch: vi.fn(async (path: string) => {
      if (path.startsWith('/api/v1/operacion/cotizar')) {
        cotizarCalls.push(path);
        if (ingresoCerrado) {
          throw new actual.ParkosHttpError(404, '{"error":"ingreso_no_encontrado"}', path);
        }
        return {
          cobrar: false,
          motivo: 'mensualidad_vigente',
          subtotal: 8100,
          iva: 1900,
          total: 10000,
          tiempo_minutos: 90,
          tarifa_uuid: UUID_TARIFA,
          vigente_hasta: '2026-09-19T11:00:00Z',
          uuid_subscripcion_cliente: UUID_SUBS,
          concepto_descuento: 'Plan Oro',
        };
      }
      throw new Error(`unexpected parkosFetch ${path}`);
    }),
  };
});

const mockTriggerSalida = vi.fn();
vi.mock('../hooks/useRegistrarSalida', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../hooks/useRegistrarSalida')>();
  return {
    ...actual,
    useRegistrarSalida: () => ({
      trigger: (...a: unknown[]) => mockTriggerSalida(...a),
      isMutating: false,
      error: undefined,
      data: undefined,
    }),
  };
});

const mockTriggerPago = vi.fn();
vi.mock('../../facturacion/hooks/useRegistrarPago', () => ({
  useRegistrarPago: () => ({
    trigger: (...a: unknown[]) => mockTriggerPago(...a),
    isMutating: false,
    error: undefined,
    data: undefined,
  }),
}));

vi.mock('../../facturacion/components/FacturaDisplayModal', () => ({
  FacturaDisplayModal: ({ factura, onClose }: { factura: unknown; onClose: () => void }) =>
    factura ? (
      <button type="button" data-testid="factura-display-cerrar" onClick={onClose}>
        Cerrar
      </button>
    ) : null,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('@parkos/ui-kit/hooks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@parkos/ui-kit/hooks')>();
  return { ...actual, useAuth: () => ({ sucursal: { uuid: 'suc-uuid-1' } }) };
});

vi.mock('../hooks/useIngresosActivos', () => ({ useIngresosActivos: () => [] }));

vi.mock('../../caja/hooks/useSesionActiva', () => ({
  useSesionActiva: () => ({ sesion: { uuid: 'ses-uuid-1' } }),
}));

vi.mock('../hooks/useInvalidateConteosOperacion', () => ({
  useInvalidateConteosOperacion: () => vi.fn().mockResolvedValue(undefined),
}));

vi.mock('../../catalogos/hooks/useTarifaByUuid', () => ({
  isUsableTarifaUuid: () => false,
  useTarifaByUuid: () => ({ tarifa: null }),
}));

import { useAuthStore } from '@parkos/ui-kit/store';
import { useDashboardDrawerStore } from '@/store/dashboardDrawerStore';
import { SalidaPanel } from './SalidaPanel';

let clearCotizarCache: (() => Promise<unknown>) | null = null;
function CacheHandle(): null {
  const { mutate } = useSWRConfig();
  clearCotizarCache = () =>
    mutate((k: unknown) => typeof k === 'string' && k.includes('/operacion/cotizar'), undefined, {
      revalidate: false,
    });
  return null;
}

function renderPanel(): void {
  render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      <CacheHandle />
      <SalidaPanel uuid_ingreso={UUID_INGRESO} />
    </SWRConfig>,
  );
}

beforeEach(() => {
  cleanup();
  ingresoCerrado = false;
  cotizarCalls.length = 0;
  mockTriggerSalida.mockReset();
  mockTriggerPago.mockReset();
  useAuthStore.setState({ accessToken: 'token-test' } as never);
  useDashboardDrawerStore.getState().close();
  useDashboardDrawerStore.getState().open('salida', 'anchor-salida');

  mockTriggerSalida.mockImplementation(async () => {
    // Server side: the ingreso is closed from now on.
    ingresoCerrado = true;
    return { uuid: '44444444-4444-4444-8444-444444444444', tipo_salida: 'MENSUALIDAD' };
  });
  mockTriggerPago.mockResolvedValue({ uuid: 'fa01', numero_recibo: 'R-1', total: 0 });
});

describe('D2 — <SalidaPanel /> mensualidad exit with the real SWR cotizacion', () => {
  it('shows the factura modal after confirming (the panel must not unmount SalidaMensualidad)', async () => {
    renderPanel();
    const confirmar = await screen.findByTestId('cotizacion-confirmar');

    fireEvent.click(confirmar);

    expect(await screen.findByTestId('factura-display-cerrar')).toBeInTheDocument();
  });

  it('closes the drawer once the factura modal is dismissed', async () => {
    renderPanel();
    const confirmar = await screen.findByTestId('cotizacion-confirmar');
    fireEvent.click(confirmar);

    const cerrar = await screen.findByTestId('factura-display-cerrar');
    fireEvent.click(cerrar);

    await waitFor(() => {
      expect(useDashboardDrawerStore.getState().openDrawer).toBeNull();
    });
  });

  it('cannot fire a second exit: the confirm button is gone/disabled after success', async () => {
    renderPanel();
    const confirmar = await screen.findByTestId('cotizacion-confirmar');
    fireEvent.click(confirmar);
    await screen.findByTestId('factura-display-cerrar');

    const again = screen.queryByTestId('cotizacion-confirmar');
    if (again) {
      expect(again).toBeDisabled();
      fireEvent.click(again);
    }
    expect(mockTriggerSalida).toHaveBeenCalledTimes(1);
  });
  it('survives the cotizar cache being cleared right when the salida resolves (the real-app race)', async () => {
    // The H7 mutate empties the SWR entry; SWR reports it before the
    // panel's own state commits. Reproduce by clearing inside the trigger.
    mockTriggerSalida.mockImplementation(async () => {
      ingresoCerrado = true;
      await clearCotizarCache?.();
      return { uuid: '44444444-4444-4444-8444-444444444444', tipo_salida: 'MENSUALIDAD' };
    });
    renderPanel();
    const confirmar = await screen.findByTestId('cotizacion-confirmar');
    fireEvent.click(confirmar);

    const cerrar = await screen.findByTestId('factura-display-cerrar');
    fireEvent.click(cerrar);
    await waitFor(() => {
      expect(useDashboardDrawerStore.getState().openDrawer).toBeNull();
    });
  });

  it('does not render a stale cotizar error banner after the exit', async () => {
    renderPanel();
    const confirmar = await screen.findByTestId('cotizacion-confirmar');
    fireEvent.click(confirmar);
    await screen.findByTestId('factura-display-cerrar');
    expect(screen.queryByTestId('cotizacion-error-banner')).not.toBeInTheDocument();
  });
});
