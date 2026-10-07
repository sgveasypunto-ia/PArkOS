/**
 * Tests for `<Venta />` wizard page (HU-F9.1, REQ-OPS-176; PT-1 / PT-2).
 *
 * Wizard of 6 steps: cliente -> tipo de vehículo -> plan -> cantidad ->
 * placas -> pago.
 *
 * Coverage:
 *   T1-T3: step 1 (cliente) rendering + validation.
 *   T4: 422 typed error from the charge -> revert to step 5 (Placas).
 *   T5: full flow reaches step 6 (Pago).
 *   T6: step 6 charges the FULL plan (PT-3) and defaults the start date to
 *       today in Bogota.
 *   T7: confirm -> `useVentaSuscripcion.trigger` called with the payload.
 *   T8/T9: receipt (+ FE state / pending notice) after the charge.
 *   T10 (PT-2): only plans of the chosen vehicle type are requested/shown.
 *   T11 (PT-1): "Volver" goes back EXACTLY one step keeping the data.
 *   T12 (PT-1): the payment draft survives a back/forward trip.
 *   T13 (PT-1): once charged, no "Volver" and no second payment.
 *   T14 (PT-2): plate format must match the chosen vehicle type.
 *
 * The PagoModal composition is stubbed: it only exposes its props.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, cleanup, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import type * as UseVentaSuscripcionModule from '../hooks/useVentaSuscripcion';

vi.mock('react-i18next', () => ({
  // Devuelve la key cruda, salvo cuando hay valores a interpolar (línea del
  // desglose de IVA): ahí aplica el defaultValue con sus {{variables}}.
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts && typeof opts.defaultValue === 'string' && 'porcentaje' in opts
        ? opts.defaultValue.replace(/\{\{(\w+)\}\}/g, (_m, k: string) => String(opts[k]))
        : key,
  }),
}));

const mockTrigger = vi.fn();
const mockIsMutating = vi.fn(() => false);
vi.mock('../hooks/useVentaSuscripcion', async (importOriginal) => {
  const actual = await importOriginal<typeof UseVentaSuscripcionModule>();
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

// El precio del plan INCLUYE el IVA (clientes_venta.py: total == plan.valor);
// el wizard pasa a <PagoModal> el valor del plan y solo muestra el desglose
// del IVA como línea informativa.
const mockIvaPorcentaje = vi.fn((): number | null => 0.19);
vi.mock('../../facturacion/hooks/useIvaVigente', () => ({
  useIvaVigente: () => ({
    porcentaje: mockIvaPorcentaje(),
    isLoading: mockIvaPorcentaje() === null,
    error: undefined,
  }),
}));

const TIPO_MOTO = '00000000-0000-0000-0000-00000000aa01';
const TIPO_CARRO = '00000000-0000-0000-0000-00000000aa02';
const PLAN_CARRO = '00000000-0000-0000-0000-0000000000a1';
const PLAN_MOTO = '00000000-0000-0000-0000-0000000000a2';
const PLAN_ANY = '00000000-0000-0000-0000-0000000000a3';

const PLANES = [
  { uuid: PLAN_CARRO, tipo: 'MENSUAL_CARRO', uuid_tipo_vehiculo: TIPO_CARRO },
  { uuid: PLAN_MOTO, tipo: 'MENSUAL_MOTO', uuid_tipo_vehiculo: TIPO_MOTO },
  { uuid: PLAN_ANY, tipo: 'MENSUAL_CUALQUIERA', uuid_tipo_vehiculo: null },
].map((p) => ({
  ...p,
  valor: 30000,
  duracion_dias: 30,
  cantidad_maxima_vehiculos: 1,
  mismo_tipo_vehiculo: true,
  tipo_cliente_permitido: 'natural',
}));

// Mirrors the backend filter: plans of that type + the NULL-type ones; `null`
// (type not chosen yet) means nothing is fetched.
const mockUseTiposSubscripciones = vi.fn((_suc: string | null, tipo?: string | null) => ({
  data:
    tipo === null
      ? undefined
      : PLANES.filter((p) => tipo === undefined || !p.uuid_tipo_vehiculo || p.uuid_tipo_vehiculo === tipo),
  error: undefined,
  refresh: async () => undefined,
  isLoading: false,
}));
vi.mock('../hooks/useTiposSubscripciones', () => ({
  useTiposSubscripciones: (suc: string | null, tipo?: string | null) =>
    mockUseTiposSubscripciones(suc, tipo),
}));

vi.mock('../../catalogos/hooks/useTiposVehiculo', () => ({
  useTiposVehiculo: () => ({
    tipos: [
      { uuid: '00000000-0000-0000-0000-00000000aa01', tipo: 'moto', vigente_desde: '', vigente_hasta: null, estado: 'activo' },
      { uuid: '00000000-0000-0000-0000-00000000aa02', tipo: 'carro', vigente_desde: '', vigente_hasta: null, estado: 'activo' },
    ],
    isLoading: false,
    error: undefined,
    refresh: async () => undefined,
    isFromFallback: false,
  }),
}));

interface PagoStubProps {
  total_cop: number;
  onSubmit: (v: unknown) => Promise<void>;
  draft?: { monto_recibido_cop?: number } | null;
  onDraftChange?: (v: unknown) => void;
  clientePrefill?: { fe?: boolean };
}
vi.mock('../../facturacion/components/PagoModal', () => ({
  PagoModal: ({ onSubmit, total_cop, draft, onDraftChange, clientePrefill }: PagoStubProps) => (
    <div data-testid="pago-modal">
      <span data-testid="pago-total">{total_cop}</span>
      <span data-testid="pago-prefill-fe">{String(clientePrefill?.fe ?? false)}</span>
      <span data-testid="pago-draft">{String(draft?.monto_recibido_cop ?? '')}</span>
      <button
        type="button"
        data-testid="pago-editar-stub"
        onClick={() =>
          onDraftChange?.({ medio_pago: 'efectivo', monto_recibido_cop: 99999, fe: false })
        }
      >
        editar
      </button>
      <button
        type="button"
        data-testid="pago-confirmar-stub"
        onClick={() =>
          onSubmit({
            medio_pago: 'efectivo',
            monto_recibido_cop: total_cop,
            // Mirrors the real PagoModal default: `p?.fe ?? false`.
            fe: clientePrefill?.fe ?? false,
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

const renderVenta = (props: Parameters<typeof Venta>[0] = {}): ReturnType<typeof render> =>
  render(
    <MemoryRouter>
      <Venta {...props} />
    </MemoryRouter>,
  );

// NOTE: every selection and its "Siguiente" click MUST be separate act()
// calls: React 18 batches state updates inside one synchronous block, so a
// same-block "Siguiente" would read the PRE-selection closure.
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
async function paso1(): Promise<void> {
  await change('venta-cliente-numero', '900123456');
  await change('venta-cliente-nombre', 'ACME');
  await click('venta-paso-1-siguiente');
}
async function paso2(tipo: string = TIPO_CARRO): Promise<void> {
  await click(`venta-tipo-vehiculo-${tipo}`);
  await click('venta-paso-2-siguiente');
}
async function paso3(plan: string = PLAN_CARRO): Promise<void> {
  await click(`venta-plan-${plan}`);
  await click('venta-paso-3-siguiente');
}
async function paso4(): Promise<void> {
  await change('venta-cantidad-input', '1');
  await click('venta-paso-4-siguiente');
}
async function paso5(placa = 'ABC123'): Promise<void> {
  await change('venta-placa-input-0', placa);
  await click('venta-paso-5-siguiente');
}
async function hastaPago(): Promise<void> {
  await paso1();
  await paso2();
  await paso3();
  await paso4();
  await paso5();
}

const FACTURA_BASE = {
  uuid: 'f0000000-0000-0000-0000-000000000001',
  created_at: '2026-09-25T10:00:00.000Z',
  uuid_sucursal: '00000000-0000-0000-0000-0000000000f1',
  uuid_ingreso: null,
  uuid_salida: null,
  numero_recibo: 'suc-20260925-000001',
  subtotal: 30000,
  descuento: 0,
  total: 35700,
  uuid_cliente: '00000000-0000-0000-0000-0000000000c1',
  items: [],
  estado: 'emitida' as const,
  medio_pago: 'efectivo' as const,
  monto_recibido_cents: null,
  vuelto_cents: null,
  voucher: null,
  cliente: null,
  datos_sucursal: {
    razon_social: 'Sede Test',
    nit: null,
    direccion: null,
    ciudad: null,
    telefono: null,
    horario: null,
    regimen: null,
  },
  datos_vehiculo: null,
  impuestos: [],
  pagos: [],
  factura_electronica: null,
};

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  mockIsMutating.mockReturnValue(false);
  mockTrigger.mockResolvedValue({
    uuid_subscripcion: '00000000-0000-0000-0000-0000000000b1',
    uuid_cliente: '00000000-0000-0000-0000-0000000000c1',
    uuid_vehiculos: ['00000000-0000-0000-0000-0000000000e1'],
    uuid_factura: '00000000-0000-0000-0000-0000000000d1',
    monto_prorrateado: null,
  });
});

describe('<Venta /> — wizard 6 pasos: cliente -> tipo -> plan -> cantidad -> placas -> pago', () => {
  it('T1: mount -> shows step 1 (cliente form)', () => {
    renderVenta();
    expect(screen.getByTestId('venta-paso-1')).toBeDefined();
    expect(screen.getByTestId('venta-cliente-numero')).toBeDefined();
  });

  it('T2: step 1 submit with valid cliente -> advances to step 2 (Tipo de vehículo)', async () => {
    renderVenta();
    await paso1();
    expect(screen.getByTestId('venta-paso-2')).toBeDefined();
    expect(screen.getByTestId('venta-paso-2-tipos')).toBeDefined();
  });

  it('T3: step 1 submit with NIT corto -> inline Zod error', async () => {
    renderVenta();
    await change('venta-cliente-numero', '123');
    await click('venta-paso-1-siguiente');
    expect(screen.queryByTestId('venta-paso-2')).toBeNull();
    expect(screen.getByTestId('venta-cliente-numero-error').textContent).toMatch(/al menos 5 caracteres/);
  });

  it('T4: pago submit -> 422 typed error -> revert to step 5 (Placas) with inline placa group error', async () => {
    const mod = await import('../hooks/useVentaSuscripcion');
    mockTrigger.mockRejectedValueOnce(new mod.VentaSuscripcionDuplicatePlateError('ABC123'));

    renderVenta();
    await hastaPago();
    await click('pago-confirmar-stub');
    // Reverts to the placas step keeping the rest of the wizard state.
    expect(screen.getByTestId('venta-paso-5')).toBeDefined();
    expect(screen.getByTestId('venta-placas-error').textContent).toMatch(/duplicada|placa/i);
    expect((screen.getByTestId('venta-placa-input-0') as HTMLInputElement).value).toBe('ABC123');
  });

  it('T5: cliente + tipo + plan + cantidad + placas -> advances to step 6 (Pago)', async () => {
    renderVenta();
    await hastaPago();
    expect(screen.getByTestId('venta-paso-6')).toBeDefined();
  });

  it('T5b: el pago se monta con el valor del plan aunque el IVA aun no cargue (sin desglose)', async () => {
    mockIvaPorcentaje.mockReturnValue(null);
    try {
      renderVenta();
      await hastaPago();
      expect(screen.getByTestId('pago-modal')).toBeDefined();
      expect(screen.getByTestId('pago-total').textContent).toBe('30000');
      expect(screen.queryByTestId('venta-iva-incluido')).toBeNull();
    } finally {
      mockIvaPorcentaje.mockReturnValue(0.19);
    }
  });

  it('T5c: muestra "Incluye IVA 19%" como desglose dentro del total, sin cobro extra', async () => {
    renderVenta();
    await hastaPago();
    const linea = screen.getByTestId('venta-iva-incluido').textContent ?? '';
    expect(linea).toMatch(/Incluye IVA 19%/);
    // 30000 / 1.19 = base 25210.08 + IVA 4789.92
    expect(linea).toMatch(/4\.789,92/);
    expect(linea).toMatch(/25\.210,08/);
    expect(screen.getByTestId('pago-total').textContent).toBe('30000');
  });

  it('T6: last day of month charges the full plan, no badge, start date = today Bogota', async () => {
    // 2026-09-30 20:00 Bogota == 2026-10-01T01:00Z (UTC is already next month).
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-10-01T01:00:00Z'));
    try {
      renderVenta();
      await hastaPago();
      expect(screen.getByTestId('pago-modal')).toBeDefined();
      // El plan (30000) ya incluye el IVA: monto recibido por defecto = valor del plan.
      expect(screen.getByTestId('pago-total').textContent).toBe('30000');
      expect(screen.queryByTestId('venta-prorrateo-badge')).toBeNull();
      await click('pago-confirmar-stub');
      const arg = mockTrigger.mock.calls[0]?.[0] as { fecha_inicio_cobertura: string };
      expect(arg.fecha_inicio_cobertura).toBe('2026-09-30');
    } finally {
      vi.useRealTimers();
    }
  });

  it('T7: confirm -> useVentaSuscripcion.trigger called with full payload', async () => {
    renderVenta();
    await hastaPago();
    await click('pago-confirmar-stub');
    expect(mockTrigger).toHaveBeenCalledTimes(1);
    const arg = mockTrigger.mock.calls[0]?.[0] as {
      cliente: { tipo_identificador: string; numero_identificacion: string };
      placas: string[];
      uuid_tipo_subscripcion: string;
      cobrar_ahora: boolean;
      emitir_factura_electronica: boolean;
    };
    expect(arg.cliente.tipo_identificador).toBe('NIT');
    expect(arg.cliente.numero_identificacion).toBe('900123456');
    expect(arg.placas).toEqual(['ABC123']);
    expect(arg.uuid_tipo_subscripcion).toBe(PLAN_CARRO);
    expect(arg.cobrar_ahora).toBe(true);
    // The FE is always emitted by the backend; `false` = standard customer.
    expect(arg.emitir_factura_electronica).toBe(false);
  });

  it('T7b: la factura a nombre del cliente llega desmarcada por defecto', async () => {
    renderVenta();
    await hastaPago();
    expect(screen.getByTestId('pago-prefill-fe').textContent).toBe('false');
  });

  it('T8: pago con cobro -> muestra <FacturaDisplayModal /> y solo completa/imprime al cerrarlo', async () => {
    mockTrigger.mockResolvedValueOnce({
      uuid_subscripcion: '00000000-0000-0000-0000-0000000000b1',
      uuid_cliente: '00000000-0000-0000-0000-0000000000c1',
      uuid_vehiculos: ['00000000-0000-0000-0000-0000000000e1'],
      uuid_factura: FACTURA_BASE.uuid,
      monto_prorrateado: null,
      factura: {
        ...FACTURA_BASE,
        factura_electronica: {
          uuid: 'fe000000-0000-0000-0000-000000000001',
          prefijo: 'SETP',
          consecutivo: 7,
          estado_dian: 'pendiente' as const,
          cufe: null,
        },
      },
      factura_electronica_error: null,
    });
    const firePrintEnvelope = vi.fn();
    const onSuccess = vi.fn();

    renderVenta({ firePrintEnvelope, onSuccess });
    await hastaPago();
    await click('pago-confirmar-stub');

    expect(screen.getByTestId('factura-display-modal')).toBeDefined();
    expect(screen.getByTestId('factura-display-total').textContent).toContain('35.700');
    // FE emitted (state shown) and NOT pending -> no warning.
    expect(screen.getByTestId('factura-display-fe').textContent).toContain('SETP');
    expect(screen.queryByTestId('factura-display-warning')).toBeNull();
    expect(onSuccess).not.toHaveBeenCalled();

    await act(async () => {
      fireEvent.click(screen.getByTestId('factura-display-cerrar'));
      await Promise.resolve();
    });

    expect(firePrintEnvelope).toHaveBeenCalledWith(
      'recibo_pago',
      expect.objectContaining({
        uuid_factura: FACTURA_BASE.uuid,
        numero_recibo: FACTURA_BASE.numero_recibo,
      }),
    );
    expect(onSuccess).toHaveBeenCalledTimes(1);
  });

  it('T9: FE pendiente -- la venta se muestra igual, con aviso no bloqueante "se reintenta sola"', async () => {
    mockTrigger.mockResolvedValueOnce({
      uuid_subscripcion: '00000000-0000-0000-0000-0000000000b1',
      uuid_cliente: '00000000-0000-0000-0000-0000000000c1',
      uuid_vehiculos: ['00000000-0000-0000-0000-0000000000e1'],
      uuid_factura: FACTURA_BASE.uuid,
      monto_prorrateado: null,
      factura: {
        ...FACTURA_BASE,
        factura_electronica_error: 'resolucion_facturacion_no_encontrada',
        factura_electronica_pendiente: true,
      },
      factura_electronica_error: 'resolucion_facturacion_no_encontrada',
    });

    renderVenta();
    await hastaPago();
    await click('pago-confirmar-stub');

    expect(screen.getByTestId('factura-display-modal')).toBeDefined();
    // react-i18next is mocked to return the raw key (not the defaultValue).
    const warning = screen.getByTestId('factura-display-warning').textContent ?? '';
    expect(warning).toContain('fe.aviso.pendiente');
    expect(warning).toContain('resolucionNoEncontrada');
  });

  it('T10 (PT-2): plans are requested/shown ONLY for the chosen vehicle type (+ type-agnostic)', async () => {
    renderVenta();
    await paso1();
    // Before choosing a type nothing is fetched (null gate), no plan list yet.
    expect(mockUseTiposSubscripciones).toHaveBeenLastCalledWith(null, null);
    await paso2(TIPO_MOTO);
    expect(mockUseTiposSubscripciones).toHaveBeenLastCalledWith(null, TIPO_MOTO);
    expect(screen.getByTestId(`venta-plan-${PLAN_MOTO}`)).toBeDefined();
    expect(screen.getByTestId(`venta-plan-${PLAN_ANY}`)).toBeDefined();
    expect(screen.queryByTestId(`venta-plan-${PLAN_CARRO}`)).toBeNull();
  });

  it('T11 (PT-1): "Volver" goes back EXACTLY one step and keeps the captured data', async () => {
    const onCancel = vi.fn();
    renderVenta({ onCancel });
    await hastaPago();
    expect(screen.getByTestId('venta-paso-6')).toBeDefined();

    // 6 -> 5 (placas intact)
    await click('venta-volver');
    expect(screen.getByTestId('venta-paso-5')).toBeDefined();
    expect((screen.getByTestId('venta-placa-input-0') as HTMLInputElement).value).toBe('ABC123');

    // 5 -> 4 (cantidad intact)
    await click('venta-volver');
    expect(screen.getByTestId('venta-paso-4')).toBeDefined();
    expect((screen.getByTestId('venta-cantidad-input') as HTMLInputElement).value).toBe('1');

    // 4 -> 3 (plan still selected)
    await click('venta-volver');
    expect(screen.getByTestId('venta-paso-3')).toBeDefined();
    expect(screen.getByTestId(`venta-plan-${PLAN_CARRO}`).getAttribute('aria-pressed')).toBe('true');

    // 3 -> 2 (tipo still selected)
    await click('venta-volver');
    expect(screen.getByTestId('venta-paso-2')).toBeDefined();
    expect(
      screen.getByTestId(`venta-tipo-vehiculo-${TIPO_CARRO}`).getAttribute('aria-checked'),
    ).toBe('true');

    // 2 -> 1 (cliente intact), never to the list nor to step 1 directly before
    await click('venta-volver');
    expect(screen.getByTestId('venta-paso-1')).toBeDefined();
    expect((screen.getByTestId('venta-cliente-numero') as HTMLInputElement).value).toBe('900123456');
    expect(onCancel).not.toHaveBeenCalled();

    // Step 1: "Volver" leaves the wizard (back to the list).
    await click('venta-volver');
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  // H8: "Volver" must never jump to the start/list from a mid-flow step.
  // One test per step so a failure names the offending step.
  describe.each([
    { from: 6, to: 5, label: 'payment -> plates' },
    { from: 5, to: 4, label: 'plate registration -> quantity' },
    { from: 4, to: 3, label: 'quantity -> plan' },
    { from: 3, to: 2, label: 'plan -> vehicle type' },
    { from: 2, to: 1, label: 'vehicle type -> client' },
  ])('H8: "Volver" from step $from ($label)', ({ from, to }) => {
    it(`lands on step ${to} and does not leave the wizard`, async () => {
      const onCancel = vi.fn();
      renderVenta({ onCancel });
      await hastaPago();
      for (let paso = 6; paso > from; paso -= 1) {
        await click('venta-volver');
      }
      expect(screen.getByTestId(`venta-paso-${from}`)).toBeDefined();

      await click('venta-volver');

      expect(screen.getByTestId(`venta-paso-${to}`)).toBeDefined();
      expect(screen.queryByTestId(`venta-paso-${from}`)).toBeNull();
      expect(onCancel).not.toHaveBeenCalled();
    });
  });

  it('H8: "Volver" on a plate validation error stays one step back, not at the start', async () => {
    const onCancel = vi.fn();
    renderVenta({ onCancel });
    await hastaPago();
    await click('venta-volver'); // 5
    await change('venta-placa-input-0', '');
    await click('venta-paso-5-siguiente'); // invalid plate: stays on 5
    expect(screen.getByTestId('venta-paso-5')).toBeDefined();

    await click('venta-volver');

    expect(screen.getByTestId('venta-paso-4')).toBeDefined();
    expect(onCancel).not.toHaveBeenCalled();
  });

  it('T11b (PT-1): the page route (no onCancel) has no "Volver" on step 1', () => {
    renderVenta();
    expect(screen.queryByTestId('venta-volver')).toBeNull();
  });

  it('T11c (PT-1/PT-2): changing the vehicle type invalidates plan/cantidad/placas only then', async () => {
    renderVenta({ onCancel: vi.fn() });
    await hastaPago();
    await click('venta-volver'); // 5
    await click('venta-volver'); // 4
    await click('venta-volver'); // 3
    await click('venta-volver'); // 2
    // Same type again -> everything below is preserved.
    await click('venta-paso-2-siguiente');
    expect(screen.getByTestId(`venta-plan-${PLAN_CARRO}`).getAttribute('aria-pressed')).toBe('true');
    await click('venta-volver'); // 2
    // Different type -> the previous plan is gone from the catalog and selection.
    await click(`venta-tipo-vehiculo-${TIPO_MOTO}`);
    await click('venta-paso-2-siguiente');
    expect(screen.queryByTestId(`venta-plan-${PLAN_CARRO}`)).toBeNull();
    expect(screen.getByTestId(`venta-plan-${PLAN_MOTO}`).getAttribute('aria-pressed')).toBe('false');
    expect((screen.getByTestId('venta-paso-3-siguiente') as HTMLButtonElement).disabled).toBe(true);
  });

  it('T12 (PT-1): the payment draft is kept across a back/forward trip', async () => {
    renderVenta({ onCancel: vi.fn() });
    await hastaPago();
    expect(screen.getByTestId('pago-draft').textContent).toBe('');
    await click('pago-editar-stub');
    await click('venta-volver'); // 5
    await click('venta-paso-5-siguiente'); // 6 again
    expect(screen.getByTestId('pago-draft').textContent).toBe('99999');
  });

  it('T13 (PT-1): once charged there is no "Volver" and the payment cannot be re-sent', async () => {
    mockTrigger.mockResolvedValueOnce({
      uuid_subscripcion: '00000000-0000-0000-0000-0000000000b1',
      uuid_cliente: '00000000-0000-0000-0000-0000000000c1',
      uuid_vehiculos: ['00000000-0000-0000-0000-0000000000e1'],
      uuid_factura: FACTURA_BASE.uuid,
      monto_prorrateado: null,
      factura: FACTURA_BASE,
      factura_electronica_error: null,
    });
    renderVenta({ onCancel: vi.fn() });
    await hastaPago();
    await click('pago-confirmar-stub');
    expect(mockTrigger).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId('venta-volver')).toBeNull();
    // The payment step is gone: the stub (second submit) is unreachable.
    expect(screen.queryByTestId('pago-confirmar-stub')).toBeNull();
  });

  it('T14 (PT-2): a car plate is rejected when the vehicle type is moto', async () => {
    renderVenta();
    await paso1();
    await paso2(TIPO_MOTO);
    await paso3(PLAN_MOTO);
    await paso4();
    await paso5('ABC123'); // auto format, type = moto
    expect(screen.getByTestId('venta-placas-format-error').textContent).toContain(
      'placa_tipo_incompatible',
    );
    expect(screen.queryByTestId('venta-paso-6')).toBeNull();
    await paso5('ABC12D'); // moto format
    expect(screen.getByTestId('venta-paso-6')).toBeDefined();
  });
});
