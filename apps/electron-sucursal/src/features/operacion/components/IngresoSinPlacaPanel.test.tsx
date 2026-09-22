/**
 * Unit tests for `<IngresoSinPlacaPanel>` (HU-INGRESO-SIN-PLACA,
 * REQ-OPS-196).
 *
 * Scenarios:
 *   - `test_renders_with_tipos`: select + Generar ingreso button visible.
 *   - `test_submit_calls_postIngreso_with_sin_placa_payload`: select a
 *     tipo, click Generar, postIngreso called with the discriminated
 *     no-placa payload.
 *   - `test_empty_state_when_no_tipos`: catalog returns empty → no submit
 *     button, degraded-UX message visible.
 *
 * The hook `useTiposVehiculoSinPlaca` is mocked via `vi.mock` so each
 * scenario controls the catalog result deterministically. The Radix
 * `<Select>` is mocked as a native `<select>` for jsdom compatibility
 * (Radix Select uses `hasPointerCapture` + portals that jsdom cannot
 * reliably emulate — same workaround pattern as `<PagoModal />` tests).
 */
import * as React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import '@/i18n';

import { IngresoSinPlacaPanel } from './IngresoSinPlacaPanel';

const useTiposVehiculoSinPlacaMock = vi.fn();

vi.mock('../../catalogos/hooks/useTiposVehiculoSinPlaca', () => ({
  useTiposVehiculoSinPlaca: () => useTiposVehiculoSinPlacaMock(),
}));

const postIngresoMock = vi.fn();

vi.mock('../lib/ingresoApi', () => ({
  postIngreso: (...args: unknown[]) => postIngresoMock(...args),
}));

/**
 * Mock the shadcn `<Select>` family as a native `<select>` for jsdom.
 * Radix Select relies on portals + pointer events that jsdom cannot
 * emulate; the native replacement preserves the contract
 * (value/onValueChange) so the consumer logic is exercised verbatim.
 * The `<select>` is rendered with only the items (no trigger/content
 * wrappers — `<select>` only accepts `<option>` children per spec).
 */
vi.mock('@/components/ui/select', () => ({
  Select: ({
    children,
    value,
    onValueChange,
    disabled,
  }: {
    children: React.ReactNode;
    value?: string;
    onValueChange?: (next: string) => void;
    disabled?: boolean;
  }) => {
    // Extract items from the children (Radix passes <SelectItem>
    // elements as children). Render them as <option> elements so the
    // browser's native <select> shows them.
    const items: React.ReactElement[] = [];
    React.Children.forEach(children, (child) => {
      if (!React.isValidElement(child)) return;
      // Drill through SelectContent to reach SelectItem.
      const contentChild = (child as React.ReactElement<{ children?: React.ReactNode }>).props.children;
      React.Children.forEach(contentChild, (item) => {
        if (React.isValidElement(item)) {
          items.push(item);
        }
      });
    });
    return (
      <select
        data-testid="native-select"
        value={value ?? ''}
        disabled={disabled}
        onChange={(e) => onValueChange?.(e.target.value)}
      >
        {items}
      </select>
    );
  },
  SelectTrigger: () => null,
  SelectValue: () => null,
  SelectContent: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
  SelectItem: ({
    value,
    children,
  }: {
    value: string;
    children: React.ReactNode;
  }) => <option value={value}>{children}</option>,
}));

const BICI_UUID = '00000000-0000-0000-0000-000000000003';
const PATIN_UUID = '00000000-0000-0000-0000-000000000004';

function makeTiposWithBici() {
  return {
    tipos: [
      {
        uuid: BICI_UUID,
        tipo: 'bicicleta',
        vigente_desde: '2026-01-01T00:00:00Z',
        vigente_hasta: null,
        estado: 'activo',
      },
      {
        uuid: PATIN_UUID,
        tipo: 'patineta',
        vigente_desde: '2026-01-01T00:00:00Z',
        vigente_hasta: null,
        estado: 'activo',
      },
    ],
    isLoading: false,
    error: undefined,
    refresh: vi.fn(),
    isFromFallback: false,
  };
}

function makeEmptyTipos() {
  return {
    tipos: [],
    isLoading: false,
    error: undefined,
    refresh: vi.fn(),
    isFromFallback: true,
  };
}

describe('<IngresoSinPlacaPanel>', () => {
  beforeEach(() => {
    postIngresoMock.mockReset();
    useTiposVehiculoSinPlacaMock.mockReset();
  });

  it('test_renders_with_tipos', () => {
    useTiposVehiculoSinPlacaMock.mockReturnValue(makeTiposWithBici());

    render(<IngresoSinPlacaPanel onSuccess={vi.fn()} />);

    expect(screen.getByTestId('ingreso-sin-placa-panel')).toBeInTheDocument();
    expect(screen.getByTestId('ingreso-sin-placa-generar')).toBeInTheDocument();
    // The mocked native select renders both options.
    expect(screen.getByTestId('native-select')).toBeInTheDocument();
  });

  it('test_submit_calls_postIngreso_with_sin_placa_payload', async () => {
    useTiposVehiculoSinPlacaMock.mockReturnValue(makeTiposWithBici());
    postIngresoMock.mockResolvedValue({
      uuid_ingreso: '11111111-2222-4333-8444-555555555555',
      tipo_entrada: 'ROTACION',
      uuid_subscripcion_cliente: null,
      consecutivo: 'BICI-000001-3f8a1b2c',
    });
    const onSuccess = vi.fn();

    render(<IngresoSinPlacaPanel onSuccess={onSuccess} />);

    // The mocked native select renders as a plain <select>. Pick "Bicicleta".
    const select = screen.getByTestId('native-select') as HTMLSelectElement;
    fireEvent.change(select, { target: { value: BICI_UUID } });

    // Click "Generar ingreso".
    const submit = screen.getByTestId('ingreso-sin-placa-generar');
    fireEvent.click(submit);

    await waitFor(() => expect(postIngresoMock).toHaveBeenCalledTimes(1));
    expect(postIngresoMock).toHaveBeenCalledWith({
      placa_presente: false,
      placa: null,
      uuid_tipo_vehiculo: BICI_UUID,
    });
    await waitFor(() => expect(onSuccess).toHaveBeenCalledTimes(1));
    expect(onSuccess).toHaveBeenCalledWith(
      expect.objectContaining({
        consecutivo: 'BICI-000001-3f8a1b2c',
      }),
    );
  });

  it('test_empty_state_when_no_tipos', () => {
    useTiposVehiculoSinPlacaMock.mockReturnValue(makeEmptyTipos());

    render(<IngresoSinPlacaPanel onSuccess={vi.fn()} />);

    expect(
      screen.getByTestId('ingreso-sin-placa-empty-state'),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId('ingreso-sin-placa-generar'),
    ).not.toBeInTheDocument();
  });
});
