/**
 * Unit tests for F7.3 — `<SalidaMensualidad />` print-envelope wiring.
 *
 * Covers REQ-OPS-160 (DEC-SUC-27 + DEC-SUC-08):
 *   - Successful 201 with `tipo_salida === 'MENSUALIDAD'` fires
 *     `bridge.imprimir('salida_mensualidad', payload)` via
 *     `queueMicrotask()` (deferred, NOT blocking the React render
 *     commit).
 *   - The print call is wrapped in `try/catch`. A thrown error from
 *     the bridge MUST be caught and logged to `console.warn` — the
 *     React render MUST NOT throw.
 *   - Non-MENSUALIDAD `tipo_salida` (e.g., `ROTACION`) does NOT
 *     trigger the print envelope.
 *
 * Purity note: the test mocks `useRegistrarSalida` (the network
 * boundary). The remaining logic is pure — render-based assertions
 * on the `<CotizacionPanel />` and side-effect assertions on the
 * `bridge.imprimir` mock.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, render, screen } from '@testing-library/react';

import { SalidaMensualidad } from './SalidaMensualidad';
import { useRegistrarSalida } from '../hooks/useRegistrarSalida';

// ──────────────────────────────────────────────────────────────────────────
// vi.mock — replace the network hook with a controllable stub
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

// ──────────────────────────────────────────────────────────────────────────
// Tests
// ──────────────────────────────────────────────────────────────────────────

describe('<SalidaMensualidad /> — print envelope wiring (HU-F7.3 / REQ-OPS-160)', () => {
  let originalBridge: unknown;

  beforeEach(() => {
    originalBridge = (globalThis as unknown as { window?: unknown }).window;
    mockTriggerImpl.mockReset();
    mockInvalidateConteos.mockReset();
  });

  afterEach(() => {
    uninstallBridgeMock();
    (globalThis as unknown as { window: unknown }).window = originalBridge;
    vi.restoreAllMocks();
  });

  it('fires bridge.imprimir("salida_mensualidad", payload) via queueMicrotask on MENSUALIDAD success', async () => {
    const bridge = installBridgeMock();

    const uuidSalida = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';
    mockTriggerImpl.mockResolvedValueOnce({
      uuid: uuidSalida,
      tipo_salida: 'MENSUALIDAD' as const,
      estado: 'MENSUALIDAD_PAGO' as const,
    });

    render(<SalidaMensualidad uuidIngreso="ingreso-uuid-001" />);

    // Click Confirmar
    await act(async () => {
      screen.getByTestId('confirmar').click();
    });
    // Drain microtasks (queueMicrotask deferred to AFTER the React commit)
    await flushMicrotasks();

    expect(mockTriggerImpl).toHaveBeenCalledTimes(1);
    expect(bridge.imprimir).toHaveBeenCalledTimes(1);
    expect(bridge.imprimir).toHaveBeenCalledWith('salida_mensualidad', expect.objectContaining({
      uuid_salida: uuidSalida,
    }));
  });

  it('does NOT fire bridge.imprimir when tipo_salida is NOT MENSUALIDAD (rotación branch — F8.1 owns)', async () => {
    const bridge = installBridgeMock();

    mockTriggerImpl.mockResolvedValueOnce({
      uuid: 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee',
      tipo_salida: 'ROTACION' as const,
      estado: 'PENDIENTE_PAGO' as const,
    });

    render(<SalidaMensualidad uuidIngreso="ingreso-uuid-002" />);

    await act(async () => {
      screen.getByTestId('confirmar').click();
    });
    await flushMicrotasks();

    expect(mockTriggerImpl).toHaveBeenCalledTimes(1);
    expect(bridge.imprimir).not.toHaveBeenCalled();
  });

  it('catches bridge.imprimir throw — logs console.warn, does not re-throw to React render', async () => {
    const bridge = installBridgeMock();
    const printerOfflineError = new Error('printer_offline');
    bridge.imprimir.mockImplementation(() => {
      throw printerOfflineError;
    });
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => undefined);

    mockTriggerImpl.mockResolvedValueOnce({
      uuid: 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee',
      tipo_salida: 'MENSUALIDAD' as const,
      estado: 'MENSUALIDAD_PAGO' as const,
    });

    // Suppress the React error boundary noise — the test asserts the
    // throw DOES NOT propagate.
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);

    render(<SalidaMensualidad uuidIngreso="ingreso-uuid-003" />);

    await act(async () => {
      screen.getByTestId('confirmar').click();
    });
    await flushMicrotasks();

    // The render did NOT crash — we can still find the confirmar button.
    expect(screen.getByTestId('confirmar')).toBeInTheDocument();

    // warn was called with the printer error
    expect(warnSpy).toHaveBeenCalledTimes(1);
    expect(warnSpy.mock.calls[0]?.[0]).toMatch(/bridge\.imprimir|queueMicrotask|print/);

    // React's error boundary was NOT engaged (no console.error for an unhandled throw)
    const errorBoundaryCalls = consoleErrorSpy.mock.calls.filter(
      (call) => String(call[0] ?? '').includes('The above error boundary'),
    );
    expect(errorBoundaryCalls.length).toBe(0);

    // sanity — the hook was called
    expect(mockedUseRegistrarSalida).toHaveBeenCalledTimes(1);
  });

  it('REGRESSION (2026-09-22): invalidates the live-count SWR caches after a successful MENSUALIDAD salida', async () => {
    installBridgeMock();

    mockTriggerImpl.mockResolvedValueOnce({
      uuid: 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee',
      tipo_salida: 'MENSUALIDAD' as const,
      estado: 'MENSUALIDAD_PAGO' as const,
    });

    render(<SalidaMensualidad uuidIngreso="ingreso-uuid-004" />);

    await act(async () => {
      screen.getByTestId('confirmar').click();
    });
    await flushMicrotasks();

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

    render(<SalidaMensualidad uuidIngreso="ingreso-uuid-005" />);

    await act(async () => {
      screen.getByTestId('confirmar').click();
    });
    await flushMicrotasks();

    // The invalidation fires regardless of `tipo_salida` — the
    // ingreso is closed either way, so the active counts (cupos
    // libres / vehiculos dentro) must refresh immediately.
    expect(mockInvalidateConteos).toHaveBeenCalledWith({
      uuid_sucursal: '00000000-0000-0000-0000-00000000br01',
      uuid_sesion: '00000000-0000-0000-0000-00000000se01',
    });
  });
});
