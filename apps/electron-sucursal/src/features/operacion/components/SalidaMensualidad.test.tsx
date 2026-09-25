/**
 * Unit tests for F7.3 — `<SalidaMensualidad />` print-envelope wiring.
 *
 * MIGRATION 0050 (operator directive 2026-09-24): a subscribed exit
 * now builds a discount factura (full breakdown + a discount line
 * netting to $0) via `POST /facturacion/factura`
 * (`medio_pago='suscripcion'`), opens `<FacturaDisplayModal />` with
 * the result, and fires the CU-15SM print envelope only AFTER the
 * operator dismisses that modal — NOT immediately after the salida
 * POST resolves (the pre-migration-0050 behavior).
 *
 * Covers REQ-OPS-160 (DEC-SUC-27 + DEC-SUC-08) + the new discount-
 * factura flow:
 *   - Successful 201 with `tipo_salida === 'MENSUALIDAD'` builds the
 *     servicio+descuento items from the `cotizacion` prop, POSTs the
 *     $0 factura, and opens the modal.
 *   - Dismissing the modal fires `bridge.imprimir('salida_mensualidad',
 *     payload)` via `queueMicrotask()` (deferred, NOT blocking the
 *     React render commit).
 *   - The print call is wrapped in `try/catch`. A thrown error from
 *     the bridge MUST be caught and logged to `console.warn` — the
 *     React render MUST NOT throw.
 *   - Non-MENSUALIDAD `tipo_salida` (e.g., `ROTACION`) does NOT touch
 *     the factura/modal/print flow at all (F8.1 owns that path).
 *
 * Purity note: the test mocks `useRegistrarSalida` + `useRegistrarPago`
 * (the network boundary) and `<FacturaDisplayModal />` (heavy
 * dependencies). The remaining logic is pure — render-based
 * assertions on the `<CotizacionPanel />` stub and side-effect
 * assertions on the `bridge.imprimir` mock.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, render, screen } from '@testing-library/react';

import { SalidaMensualidad } from './SalidaMensualidad';
import { useRegistrarSalida } from '../hooks/useRegistrarSalida';
import type { CotizarMensualidad } from '../hooks/useCotizacion';

// ──────────────────────────────────────────────────────────────────────────
// vi.mock — replace the network hooks with controllable stubs
// ──────────────────────────────────────────────────────────────────────────

const mockTriggerImpl = vi.fn();
vi.mock('../hooks/useRegistrarSalida', () => ({
  useRegistrarSalida: vi.fn(() => ({
    trigger: (...args: unknown[]) => mockTriggerImpl(...args),
    isMutating: false,
    error: undefined,
    data: undefined,
  })),
  SalidaDuplicadaError: class extends Error {
    public readonly status = 409;
    constructor(public readonly uuid_ingreso: string) {
      super('salida_duplicada');
      this.name = 'SalidaDuplicadaError';
    }
  },
}));

const mockTriggerPagoImpl = vi.fn();
vi.mock('../../facturacion/hooks/useRegistrarPago', () => ({
  useRegistrarPago: vi.fn(() => ({
    trigger: (...args: unknown[]) => mockTriggerPagoImpl(...args),
    isMutating: false,
    error: undefined,
    data: undefined,
  })),
}));

// REGRESSION fix (2026-09-22): the panel invalidates the live-count
// SWR caches after a successful salida. Capture the calls so we can
// assert the post-trigger invalidation fires.
const mockInvalidateConteos = vi.fn();
vi.mock('../hooks/useInvalidateConteosOperacion', () => ({
  useInvalidateConteosOperacion: () => mockInvalidateConteos,
}));

vi.mock('@parkos/ui-kit/hooks', () => ({
  useAuth: () => ({
    sucursal: { uuid: '00000000-0000-0000-0000-00000000br01' },
  }),
}));

vi.mock('../../caja/hooks/useSesionActiva', () => ({
  useSesionActiva: () => ({
    sesion: { uuid: '00000000-0000-0000-0000-00000000se01' },
  }),
}));

const mockedUseRegistrarSalida = vi.mocked(useRegistrarSalida);

// ──────────────────────────────────────────────────────────────────────────
// Stub CotizacionPanel — the real one has heavy dependencies
// ──────────────────────────────────────────────────────────────────────────

vi.mock('./CotizacionPanel', () => ({
  CotizacionPanel: ({ onConfirmar }: { onConfirmar: () => void }) => (
    <button type="button" data-testid="confirmar" onClick={onConfirmar}>
      Confirmar salida mensualidad
    </button>
  ),
}));

// ──────────────────────────────────────────────────────────────────────────
// Stub FacturaDisplayModal — the real one has heavy dependencies
// (shadcn Dialog, i18n, formatCOP). Renders a "cerrar" button that
// calls onClose only when a factura is present, mirroring the real
// component's `open = factura !== null` gate.
// ──────────────────────────────────────────────────────────────────────────

vi.mock('../../facturacion/components/FacturaDisplayModal', () => ({
  FacturaDisplayModal: ({
    factura,
    onClose,
  }: {
    factura: unknown;
    onClose: () => void;
  }) =>
    factura ? (
      <button type="button" data-testid="factura-display-cerrar" onClick={onClose}>
        Cerrar
      </button>
    ) : null,
}));

// ──────────────────────────────────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────────────────────────────────

type BridgeMock = {
  imprimir: ReturnType<typeof vi.fn>;
};

function installBridgeMock(): BridgeMock {
  const w = globalThis as unknown as {
    window?: { bridge?: { imprimir?: (k: string, p: unknown) => unknown } };
  };
  const imprimir = vi.fn();
  w.window = w.window ?? {};
  w.window.bridge = w.window.bridge ?? {};
  w.window.bridge.imprimir = imprimir as unknown as (k: string, p: unknown) => unknown;
  return { imprimir };
}

function uninstallBridgeMock(): void {
  const w = globalThis as unknown as {
    window?: { bridge?: { imprimir?: unknown } };
  };
  if (w.window?.bridge) {
    delete w.window.bridge.imprimir;
  }
}

async function flushMicrotasks(): Promise<void> {
  // Drain all pending microtasks (queueMicrotask callbacks).
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

const UUID_SUBSCRIPCION = '00000000-0000-0000-0000-00000000sc01';
const UUID_TARIFA = '00000000-0000-0000-0000-00000000ta01';

const cotizacionMensualidad: CotizarMensualidad = {
  cobrar: false,
  motivo: 'mensualidad_vigente',
  subtotal: 8100,
  iva: 1900,
  total: 10000,
  tiempo_minutos: 90,
  tarifa_uuid: UUID_TARIFA,
  vigente_hasta: '2026-09-19T11:00:00Z',
  uuid_subscripcion_cliente: UUID_SUBSCRIPCION,
  concepto_descuento: 'Plan Oro',
};

const facturaMensualidadResponse = {
  uuid: '00000000-0000-0000-0000-00000000fa01',
  numero_recibo: 'D000001-20260919-000001',
  total: 0,
  descuento: 10000,
};

// ──────────────────────────────────────────────────────────────────────────
// Tests
// ──────────────────────────────────────────────────────────────────────────

describe('<SalidaMensualidad /> — discount-factura + print envelope wiring (migration 0050 / REQ-OPS-160)', () => {
  let originalBridge: unknown;

  beforeEach(() => {
    originalBridge = (globalThis as unknown as { window?: unknown }).window;
    mockTriggerImpl.mockReset();
    mockTriggerPagoImpl.mockReset();
    mockInvalidateConteos.mockReset();
  });

  afterEach(() => {
    uninstallBridgeMock();
    (globalThis as unknown as { window: unknown }).window = originalBridge;
    vi.restoreAllMocks();
  });

  it('MENSUALIDAD success builds servicio+descuento items and POSTs the $0 factura', async () => {
    installBridgeMock();

    const uuidSalida = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';
    mockTriggerImpl.mockResolvedValueOnce({
      uuid: uuidSalida,
      tipo_salida: 'MENSUALIDAD' as const,
      estado: 'MENSUALIDAD_PAGO' as const,
    });
    mockTriggerPagoImpl.mockResolvedValueOnce(facturaMensualidadResponse);

    render(
      <SalidaMensualidad uuidIngreso="ingreso-uuid-001" cotizacion={cotizacionMensualidad} />,
    );

    await act(async () => {
      screen.getByTestId('confirmar').click();
    });

    expect(mockTriggerPagoImpl).toHaveBeenCalledTimes(1);
    expect(mockTriggerPagoImpl).toHaveBeenCalledWith({
      uuid_salida: uuidSalida,
      medio_pago: 'suscripcion',
      items: [
        { tipo: 'servicio', concepto: 'Estadía', cantidad: 1, valor_unitario: 10000 },
        {
          tipo: 'descuento',
          concepto: 'Descuento por mensualidad - Plan Oro',
          cantidad: 1,
          valor_unitario: 10000,
        },
      ],
      subtotal: 8100,
      total: 0,
    });
  });

  it('opens <FacturaDisplayModal /> with the factura result, print does NOT fire yet', async () => {
    const bridge = installBridgeMock();

    mockTriggerImpl.mockResolvedValueOnce({
      uuid: 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee',
      tipo_salida: 'MENSUALIDAD' as const,
      estado: 'MENSUALIDAD_PAGO' as const,
    });
    mockTriggerPagoImpl.mockResolvedValueOnce(facturaMensualidadResponse);

    render(
      <SalidaMensualidad uuidIngreso="ingreso-uuid-002" cotizacion={cotizacionMensualidad} />,
    );

    await act(async () => {
      screen.getByTestId('confirmar').click();
    });

    expect(screen.getByTestId('factura-display-cerrar')).toBeInTheDocument();
    expect(bridge.imprimir).not.toHaveBeenCalled();
  });

  it('fires bridge.imprimir("salida_mensualidad", payload) via queueMicrotask ONLY after the modal closes', async () => {
    const bridge = installBridgeMock();

    const uuidSalida = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';
    mockTriggerImpl.mockResolvedValueOnce({
      uuid: uuidSalida,
      tipo_salida: 'MENSUALIDAD' as const,
      estado: 'MENSUALIDAD_PAGO' as const,
    });
    mockTriggerPagoImpl.mockResolvedValueOnce(facturaMensualidadResponse);

    render(
      <SalidaMensualidad uuidIngreso="ingreso-uuid-003" cotizacion={cotizacionMensualidad} />,
    );

    await act(async () => {
      screen.getByTestId('confirmar').click();
    });
    expect(bridge.imprimir).not.toHaveBeenCalled();

    await act(async () => {
      screen.getByTestId('factura-display-cerrar').click();
    });
    await flushMicrotasks();

    expect(bridge.imprimir).toHaveBeenCalledTimes(1);
    expect(bridge.imprimir).toHaveBeenCalledWith(
      'salida_mensualidad',
      expect.objectContaining({ uuid_salida: uuidSalida }),
    );
  });

  it('does NOT touch the factura/modal/print flow when tipo_salida is NOT MENSUALIDAD (rotación branch — F8.1 owns)', async () => {
    const bridge = installBridgeMock();

    mockTriggerImpl.mockResolvedValueOnce({
      uuid: 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee',
      tipo_salida: 'ROTACION' as const,
      estado: 'PENDIENTE_PAGO' as const,
    });

    render(
      <SalidaMensualidad uuidIngreso="ingreso-uuid-004" cotizacion={cotizacionMensualidad} />,
    );

    await act(async () => {
      screen.getByTestId('confirmar').click();
    });
    await flushMicrotasks();

    expect(mockTriggerImpl).toHaveBeenCalledTimes(1);
    expect(mockTriggerPagoImpl).not.toHaveBeenCalled();
    expect(screen.queryByTestId('factura-display-cerrar')).not.toBeInTheDocument();
    expect(bridge.imprimir).not.toHaveBeenCalled();
  });

  it('catches bridge.imprimir throw — logs console.warn, does not re-throw to React render', async () => {
    const bridge = installBridgeMock();
    const printerOfflineError = new Error('printer_offline');
    bridge.imprimir.mockImplementation(() => {
      throw printerOfflineError;
    });
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    // Suppress the React error boundary noise — the test asserts the
    // throw DOES NOT propagate.
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);

    mockTriggerImpl.mockResolvedValueOnce({
      uuid: 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee',
      tipo_salida: 'MENSUALIDAD' as const,
      estado: 'MENSUALIDAD_PAGO' as const,
    });
    mockTriggerPagoImpl.mockResolvedValueOnce(facturaMensualidadResponse);

    render(
      <SalidaMensualidad uuidIngreso="ingreso-uuid-005" cotizacion={cotizacionMensualidad} />,
    );

    await act(async () => {
      screen.getByTestId('confirmar').click();
    });
    await act(async () => {
      screen.getByTestId('factura-display-cerrar').click();
    });
    await flushMicrotasks();

    // The render did NOT crash — we can still find the confirmar button.
    expect(screen.getByTestId('confirmar')).toBeInTheDocument();

    // warn was called with the printer error
    expect(warnSpy).toHaveBeenCalledTimes(1);
    expect(warnSpy.mock.calls[0]?.[0]).toMatch(/bridge\.imprimir|queueMicrotask|print/);

    // React's error boundary was NOT engaged (no console.error for an unhandled throw)
    const errorBoundaryCalls = consoleErrorSpy.mock.calls.filter((call) =>
      String(call[0] ?? '').includes('The above error boundary'),
    );
    expect(errorBoundaryCalls.length).toBe(0);

    // sanity — the hook was called (>=1; the discount-factura flow's
    // extra setState calls — pendingPrint, facturaDisplay — cause more
    // re-renders than the pre-migration-0050 print-only flow, so an
    // exact count is not the invariant worth asserting here).
    expect(mockedUseRegistrarSalida).toHaveBeenCalled();
  });

  it('REGRESSION (2026-09-22): invalidates the live-count SWR caches after a successful MENSUALIDAD salida', async () => {
    installBridgeMock();

    mockTriggerImpl.mockResolvedValueOnce({
      uuid: 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee',
      tipo_salida: 'MENSUALIDAD' as const,
      estado: 'MENSUALIDAD_PAGO' as const,
    });
    mockTriggerPagoImpl.mockResolvedValueOnce(facturaMensualidadResponse);

    render(
      <SalidaMensualidad uuidIngreso="ingreso-uuid-006" cotizacion={cotizacionMensualidad} />,
    );

    await act(async () => {
      screen.getByTestId('confirmar').click();
    });

    // Without this invalidation, the dashboard panels keep showing
    // the pre-mutation counts until the next SWR poll tick (10–15s),
    // which the operator perceived as "hardcoded" data.
    expect(mockInvalidateConteos).toHaveBeenCalledWith({
      uuid_sucursal: '00000000-0000-0000-0000-00000000br01',
      uuid_sesion: '00000000-0000-0000-0000-00000000se01',
    });
  });

  it('REGRESSION (2026-09-22): invalidates the live-count SWR caches after a successful ROTACION salida as well', async () => {
    installBridgeMock();

    mockTriggerImpl.mockResolvedValueOnce({
      uuid: 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee',
      tipo_salida: 'ROTACION' as const,
      estado: 'PENDIENTE_PAGO' as const,
    });

    render(
      <SalidaMensualidad uuidIngreso="ingreso-uuid-007" cotizacion={cotizacionMensualidad} />,
    );

    await act(async () => {
      screen.getByTestId('confirmar').click();
    });

    // The invalidation fires regardless of `tipo_salida` — the
    // ingreso is closed either way, so the active counts (cupos
    // libres / vehiculos dentro) must refresh immediately.
    expect(mockInvalidateConteos).toHaveBeenCalledWith({
      uuid_sucursal: '00000000-0000-0000-0000-00000000br01',
      uuid_sesion: '00000000-0000-0000-0000-00000000se01',
    });
  });
});
