/**
 * Smoke + structural tests for `<IngresoPanel />` (F6.1 dashboard section).
 *
 * Coverage:
 *   I1: panel renders title + PlacaInput mount.
 *   I2: PlacaInput submit invokes the panel's onValidSubmit → flow
 *       continues (mocked `postIngreso` returns a 201-shaped response).
 *   I3: `data-testid="ingreso-panel"` present per REQ-OPS-137 contract.
 *
 * The panel is a thin orchestrator over `Principal.tsx` logic; deeper
 * behaviour (TiqueteModal/ForzarIngresoModal mount on success/422) is
 * covered by `Principal.test.tsx` — this test pins only the new contract.
 */
import * as React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, render, screen, cleanup } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

// Stub the heavy dependencies — keep the test focused on the panel
// shell contract; full behavior lives in Principal.test.tsx.
vi.mock('./PlacaInput', () => ({
  PlacaInput: ({
    onValidSubmit,
    disabled,
    initialValue,
  }: {
    onValidSubmit: (placa: string) => void;
    disabled?: boolean;
    initialValue?: string | null;
  }) => (
    <button
      type="button"
      data-testid="placa-input-stub"
      data-initial-value={initialValue ?? ''}
      disabled={disabled}
      onClick={() => onValidSubmit('ABC123')}
    >
      placa-input-stub
    </button>
  ),
}));

vi.mock('./TiqueteModal', () => ({
  TiqueteModal: () => <div data-testid="tiquete-modal-stub" />,
}));

vi.mock('./ForzarIngresoModal', () => ({
  ForzarIngresoModal: () => <div data-testid="forzar-modal-stub" />,
}));

vi.mock('../../catalogos/hooks/useTiposVehiculo', () => ({
  useTiposVehiculo: () => ({
    tipos: [
      { uuid: '00000000-0000-0000-0000-000000000010', tipo: 'carro' },
      { uuid: '00000000-0000-0000-0000-000000000020', tipo: 'moto' },
    ],
    isLoading: false,
    error: undefined,
  }),
}));

const mockUseIngresoActivo = vi.fn();
vi.mock('../hooks/useIngresoActivo', () => ({
  useIngresoActivo: () => mockUseIngresoActivo(),
}));

const mockPostIngreso = vi.fn();
vi.mock('../lib/ingresoApi', () => ({
  postIngreso: (...args: unknown[]) => mockPostIngreso(...args),
}));

// window.bridge.imprimir stub — needed by `openSuccessWithAutoPrint`.
declare global {
  interface Window {
    bridge: { imprimir: (payload: unknown) => Promise<{ ok: boolean }> };
  }
}
window.bridge = {
  imprimir: vi.fn().mockResolvedValue({ ok: true }),
};

import { IngresoPanel } from './IngresoPanel';

beforeEach(() => {
  vi.clearAllMocks();
  window.bridge.imprimir = vi.fn().mockResolvedValue({ ok: true });
  mockUseIngresoActivo.mockReturnValue({
    hasActive: false,
    latestIngreso: null,
    isLoading: false,
    error: undefined,
    refresh: vi.fn(),
  });
});

afterEach(() => {
  cleanup();
});

describe('<IngresoPanel /> — F6.1 dashboard section (REQ-OPS-136)', () => {
  it('I1: panel renders title + PlacaInput on mount', () => {
    render(
      <MemoryRouter>
        <IngresoPanel />
      </MemoryRouter>,
    );
    expect(screen.getByTestId('ingreso-panel')).toBeInTheDocument();
    expect(screen.getByTestId('placa-input-stub')).toBeInTheDocument();
  });

  it('I2: two-step flujo (validate + confirmar) triggers postIngreso + auto-print on 201', async () => {
    mockPostIngreso.mockResolvedValue({
      uuid_ingreso: '00000000-0000-0000-0000-000000000777',
      tipo_entrada: 'ROTACION',
      uuid_subscripcion_cliente: null,
    });

    render(
      <MemoryRouter>
        <IngresoPanel />
      </MemoryRouter>,
    );

    // Step 1: operator submits the placa — should ONLY validate (no POST).
    await act(async () => {
      screen.getByTestId('placa-input-stub').click();
    });
    expect(mockPostIngreso).not.toHaveBeenCalled();
    expect(window.bridge.imprimir).not.toHaveBeenCalled();

    // Step 2: operator clicks "Registrar ingreso" — POST fires.
    await act(async () => {
      const registrarBtn = screen.getByTestId('ingreso-registrar') as HTMLButtonElement;
      registrarBtn.click();
    });
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(mockPostIngreso).toHaveBeenCalledWith({
      placa: 'ABC123',
      uuid_tipo_vehiculo: '00000000-0000-0000-0000-000000000010',
    });
    expect(window.bridge.imprimir).toHaveBeenCalled();
  });

  it('I3: cold mount issues zero network calls when placa stays empty', () => {
    render(
      <MemoryRouter>
        <IngresoPanel />
      </MemoryRouter>,
    );
    expect(mockPostIngreso).not.toHaveBeenCalled();
    expect(window.bridge.imprimir).not.toHaveBeenCalled();
  });

  it('I4: 422 motivo_forzado_requerido opens ForzarIngresoModal (lazy) on confirmar', async () => {
    const { ParkosHttpError } = await import('@parkos/ui-kit/fetch');
    mockPostIngreso.mockRejectedValue(
      new ParkosHttpError(422, 'motivo_forzado_requerido'),
    );

    render(
      <MemoryRouter>
        <IngresoPanel />
      </MemoryRouter>,
    );
    // Step 1: validate placa (no POST).
    await act(async () => {
      screen.getByTestId('placa-input-stub').click();
    });

    // Step 2: confirmar — POST fires, server returns 422 → Forzar modal.
    await act(async () => {
      const registrarBtn = screen.getByTestId('ingreso-registrar') as HTMLButtonElement;
      registrarBtn.click();
    });

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    // Forzar modal is mounted lazily once the 422 path triggers.
    expect(screen.getByTestId('forzar-modal-stub')).toBeInTheDocument();
  });

  it('I5: initialPlaca="ABC123" is threaded to PlacaInput as initialValue (pre-fill)', () => {
    render(
      <MemoryRouter>
        <IngresoPanel initialPlaca="ABC123" />
      </MemoryRouter>,
    );
    const stub = screen.getByTestId('placa-input-stub');
    expect(stub.getAttribute('data-initial-value')).toBe('ABC123');
    // Cold-mount invariant: the panel does NOT auto-submit when pre-filled.
    expect(mockPostIngreso).not.toHaveBeenCalled();
    expect(window.bridge.imprimir).not.toHaveBeenCalled();
  });

  it('I6: initialPlaca="ABC12D" (moto shape) is accepted and forwarded', () => {
    render(
      <MemoryRouter>
        <IngresoPanel initialPlaca="ABC12D" />
      </MemoryRouter>,
    );
    const stub = screen.getByTestId('placa-input-stub');
    expect(stub.getAttribute('data-initial-value')).toBe('ABC12D');
  });
});