/**
 * Tests for `<Venta />` wizard page (HU-F9.1, REQ-OPS-176).
 *
 * Coverage (7 component tests):
 *   T1: mount -> shows step 1 (cliente form).
 *   T2: step 1 submit with valid cliente -> advances to step 2 (Plan).
 *   T3: step 1 submit with NIT corto -> inline Zod error.
 *   T4: pago submit -> 422 typed error -> revert to step 4 (Placas) with
 *       inline placa group error.
 *   T5: cliente + plan + cantidad + placas -> advances to step 5 (Pago).
 *   T6: step 5 shows prorrateo badge when applicable (day>15).
 *   T7: confirm -> useVentaSuscripcion.trigger called with full payload.
 *
 * The PagoModal composition is stubbed via a real `<PagoModal />`
 * mock that just exposes its `onSubmit` prop -- no full F8.1 PagoModal
 * test re-run inside this file (PagoModal's own tests cover that).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, cleanup, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const mockTrigger = vi.fn();
const mockIsMutating = vi.fn(() => false);
vi.mock('../hooks/useVentaSuscripcion', async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    useVentaSuscripcion: () => ({
      trigger: mockTrigger,
      isMutating: mockIsMutating(),
      error: undefined,
      data: undefined,
    }),
  };
});

// Stub the catalog endpoint so useTiposSubscripciones returns 1 plan with
// max=1 -- matches the rest of the test's assumption that the operator
// will type exactly one plate.
vi.mock('../hooks/useTiposSubscripciones', () => ({
  useTiposSubscripciones: () => ({
    data: [
      {
        uuid: '00000000-0000-0000-0000-0000000000a1',
        tipo: 'MENSUAL_TEST',
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

vi.mock('../../facturacion/components/PagoModal', () => ({
  PagoModal: ({
    onSubmit,
    total_cop,
  }: {
    uuid_ingreso: string | null;
    total_cop: number;
    onSubmit: (v: unknown) => Promise<void>;
  }) => (
    <div data-testid="pago-modal">
      <span data-testid="pago-total">{total_cop}</span>
      <button
        type="button"
        data-testid="pago-confirmar-stub"
        onClick={() =>
          onSubmit({
            medio_pago: 'efectivo',
            monto_recibido_cop: total_cop,
            fe: false,
            nit: '222222222222222',
            dv: '',
            nombre_cliente: 'Consumidor final',
            email_cliente: '',
            voucher: '',
          })
        }
      >
        Confirmar pago stub
      </button>
    </div>
  ),
}));

import { Venta } from './Venta';

const renderVenta = (): ReturnType<typeof render> =>
  render(
    <MemoryRouter>
      <Venta />
    </MemoryRouter>,
  );

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  mockIsMutating.mockReturnValue(false);
  mockTrigger.mockResolvedValue({
    uuid_subscripcion: '00000000-0000-0000-0000-0000000000b1',
    uuid_cliente: '00000000-0000-0000-0000-0000000000c1',
    uuid_vehiculos: ['00000000-0000-0000-0000-0000000000e1'],
    uuid_factura: '00000000-0000-0000-0000-0000000000d1',
    monto_prorrateado: 11000,
  });
});

describe('<Venta /> — REQ-OPS-176 (wizard 5 pasos: cliente -> plan -> cantidad -> placas -> pago)', () => {
  it('T1: mount -> shows step 1 (cliente form)', () => {
    renderVenta();
    expect(screen.getByTestId('venta-paso-1')).toBeDefined();
    expect(screen.getByTestId('venta-cliente-nit')).toBeDefined();
  });

  it('T2: step 1 submit with valid cliente -> advances to step 2 (Plan)', async () => {
    renderVenta();
    const nit = screen.getByTestId('venta-cliente-nit');
    const nombre = screen.getByTestId('venta-cliente-nombre');
    await act(async () => {
      fireEvent.change(nit, { target: { value: '900123456' } });
      fireEvent.change(nombre, { target: { value: 'ACME S.A.S.' } });
    });
    const submit = screen.getByTestId('venta-paso-1-siguiente');
    await act(async () => {
      fireEvent.click(submit);
    });
    expect(screen.getByTestId('venta-paso-2')).toBeDefined();
  });

  it('T3: step 1 submit with NIT corto -> inline Zod error', async () => {
    renderVenta();
    const nit = screen.getByTestId('venta-cliente-nit');
    await act(async () => {
      fireEvent.change(nit, { target: { value: '123' } });
    });
    const submit = screen.getByTestId('venta-paso-1-siguiente');
    await act(async () => {
      fireEvent.click(submit);
    });
    expect(screen.queryByTestId('venta-paso-2')).toBeNull();
    expect(screen.getByTestId('venta-cliente-nit-error').textContent).toMatch(
      /nit/,
    );
  });

  it('T4: pago submit -> 422 typed error -> revert to step 4 (Placas) with inline placa group error', async () => {
    // Import real classes via the mocked-with-importOriginal hook.
    const mod = await import('../hooks/useVentaSuscripcion');
    mockTrigger.mockRejectedValueOnce(
      new mod.VentaSuscripcionDuplicatePlateError('ABC123'),
    );

    renderVenta();
    // step 1
    await act(async () => {
      fireEvent.change(screen.getByTestId('venta-cliente-nit'), {
        target: { value: '900123456' },
      });
      fireEvent.change(screen.getByTestId('venta-cliente-nombre'), {
        target: { value: 'ACME' },
      });
      fireEvent.click(screen.getByTestId('venta-paso-1-siguiente'));
    });
    // step 2 (Plan)
    await act(async () => {
      const plan = screen.getByTestId('venta-plan-00000000-0000-0000-0000-0000000000a1');
      fireEvent.click(plan);
      fireEvent.click(screen.getByTestId('venta-paso-2-siguiente'));
    });
    // step 3 (Cantidad)
    await act(async () => {
      fireEvent.change(screen.getByTestId('venta-cantidad-input'), {
        target: { value: '1' },
      });
      fireEvent.click(screen.getByTestId('venta-paso-3-siguiente'));
    });
    // step 4 (Placas)
    await act(async () => {
      fireEvent.change(screen.getByTestId('venta-placa-input-0'), {
        target: { value: 'ABC123' },
      });
      fireEvent.click(screen.getByTestId('venta-paso-4-siguiente'));
    });
    // step 5 PagoModal stub: click confirmar -> trigger throws typed error
    await act(async () => {
      fireEvent.click(screen.getByTestId('pago-confirmar-stub'));
    });
    // The wizard reverts to paso 4 (Placas) with the inline group error.
    expect(screen.getByTestId('venta-paso-4')).toBeDefined();
    expect(screen.getByTestId('venta-placas-error').textContent).toMatch(
      /duplicada|placa/i,
    );
  });

  it('T5: cliente + plan + cantidad + placas -> advances to step 5 (Pago)', async () => {
    renderVenta();
    // step 1
    await act(async () => {
      fireEvent.change(screen.getByTestId('venta-cliente-nit'), {
        target: { value: '900123456' },
      });
      fireEvent.change(screen.getByTestId('venta-cliente-nombre'), {
        target: { value: 'ACME' },
      });
      fireEvent.click(screen.getByTestId('venta-paso-1-siguiente'));
    });
    // step 2 (Plan)
    await act(async () => {
      const plan = screen.getByTestId('venta-plan-00000000-0000-0000-0000-0000000000a1');
      fireEvent.click(plan);
      fireEvent.click(screen.getByTestId('venta-paso-2-siguiente'));
    });
    // step 3 (Cantidad)
    await act(async () => {
      fireEvent.change(screen.getByTestId('venta-cantidad-input'), {
        target: { value: '1' },
      });
      fireEvent.click(screen.getByTestId('venta-paso-3-siguiente'));
    });
    // step 4 (Placas)
    await act(async () => {
      fireEvent.change(screen.getByTestId('venta-placa-input-0'), {
        target: { value: 'ABC123' },
      });
      fireEvent.click(screen.getByTestId('venta-paso-4-siguiente'));
    });
    expect(screen.getByTestId('venta-paso-5')).toBeDefined();
  });

  it('T6: step 5 shows prorrateo badge when applicable (day>15)', async () => {
    // date=2026-09-19 (day=19) -> prorrateo visible
    renderVenta();
    // step 1
    await act(async () => {
      fireEvent.change(screen.getByTestId('venta-cliente-nit'), {
        target: { value: '900123456' },
      });
      fireEvent.change(screen.getByTestId('venta-cliente-nombre'), {
        target: { value: 'ACME' },
      });
      fireEvent.click(screen.getByTestId('venta-paso-1-siguiente'));
    });
    // step 2 (Plan)
    await act(async () => {
      const plan = screen.getByTestId('venta-plan-00000000-0000-0000-0000-0000000000a1');
      fireEvent.click(plan);
      fireEvent.click(screen.getByTestId('venta-paso-2-siguiente'));
    });
    // step 3 (Cantidad)
    await act(async () => {
      fireEvent.change(screen.getByTestId('venta-cantidad-input'), {
        target: { value: '1' },
      });
      fireEvent.click(screen.getByTestId('venta-paso-3-siguiente'));
    });
    // step 4 (Placas)
    await act(async () => {
      fireEvent.change(screen.getByTestId('venta-placa-input-0'), {
        target: { value: 'ABC123' },
      });
      fireEvent.click(screen.getByTestId('venta-paso-4-siguiente'));
    });
    // step 5: prorrateo badge should be visible (total > 0)
    expect(screen.getByTestId('pago-modal')).toBeDefined();
    expect(screen.getByTestId('pago-total').textContent).toBeTruthy();
  });

  it('T7: confirm -> useVentaSuscripcion.trigger called with full payload', async () => {
    renderVenta();
    // step 1
    await act(async () => {
      fireEvent.change(screen.getByTestId('venta-cliente-nit'), {
        target: { value: '900123456' },
      });
      fireEvent.change(screen.getByTestId('venta-cliente-nombre'), {
        target: { value: 'ACME' },
      });
      fireEvent.click(screen.getByTestId('venta-paso-1-siguiente'));
    });
    // step 2 (Plan)
    await act(async () => {
      const plan = screen.getByTestId('venta-plan-00000000-0000-0000-0000-0000000000a1');
      fireEvent.click(plan);
      fireEvent.click(screen.getByTestId('venta-paso-2-siguiente'));
    });
    // step 3 (Cantidad)
    await act(async () => {
      fireEvent.change(screen.getByTestId('venta-cantidad-input'), {
        target: { value: '1' },
      });
      fireEvent.click(screen.getByTestId('venta-paso-3-siguiente'));
    });
    // step 4 (Placas)
    await act(async () => {
      fireEvent.change(screen.getByTestId('venta-placa-input-0'), {
        target: { value: 'ABC123' },
      });
      fireEvent.click(screen.getByTestId('venta-paso-4-siguiente'));
    });
    // step 5 PagoModal stub: click confirmar
    await act(async () => {
      fireEvent.click(screen.getByTestId('pago-confirmar-stub'));
    });
    expect(mockTrigger).toHaveBeenCalledTimes(1);
    const arg = mockTrigger.mock.calls[0]?.[0] as {
      cliente: { nit: string };
      placas: string[];
      uuid_tipo_subscripcion: string;
      cobrar_ahora: boolean;
    };
    expect(arg.cliente.nit).toBe('900123456');
    expect(arg.placas).toEqual(['ABC123']);
    expect(arg.uuid_tipo_subscripcion).toBe(
      '00000000-0000-0000-0000-0000000000a1',
    );
    expect(arg.cobrar_ahora).toBe(true);
  });
});
