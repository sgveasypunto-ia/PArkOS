/**
 * Tests for `<SalidaPanel />` (F7.1+F7.2 dashboard section).
 *
 * Coverage (canonical schema mocks — R4 drift reconciliation):
 *   S1: panel renders title + plate input on mount.
 *   S2: idle mode (uuid_ingreso=null) — `useCotizacion` is NOT invoked
 *       (REQ-OPS-139 lazy-mount invariant).
 *   S3: submit placa + non-null uuid_ingreso → renders `<CotizacionPanel />`
 *       with the canonical discriminated union; formatCOP output
 *       (`"$ 48.790"`) is asserted.
 *   S4: clicking "Confirmar salida" opens the pago drawer via the
 *       store (REQ-OPS-138 single-drawer invariant preserved).
 *   S5: mensualidad (cobrar:false) renders the mensualidad banner,
 *       not the `<dl>` breakdown.
 */
import * as React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const mockUseCotizacion = vi.fn();
vi.mock('../hooks/useCotizacion', () => ({
  useCotizacion: (...args: unknown[]) => mockUseCotizacion(...args),
}));

import { useDashboardDrawerStore } from '@/store/dashboardDrawerStore';
import { SalidaPanel } from './SalidaPanel';

beforeEach(() => {
  useDashboardDrawerStore.getState().close();
  mockUseCotizacion.mockReset();
  cleanup();
});

const TARIFA_UUID = '00000000-0000-0000-0000-0000000000aa';
const UUID_INGRESO_A = '00000000-0000-0000-0000-0000000000a1';
const UUID_INGRESO_B = '00000000-0000-0000-0000-0000000000b1';

const cotizacionRotacion = {
  cobrar: true as const,
  subtotal: 41000,
  iva: 7790,
  total: 48790,
  tiempo_minutos: 32.5,
  tarifa_uuid: TARIFA_UUID,
  vigente_hasta: '2026-09-19T11:00:00Z',
};

const cotizacionMensualidad = {
  cobrar: false as const,
  motivo: 'mensualidad_vigente' as const,
};

describe('<SalidaPanel /> — F7.1+F7.2 dashboard section (canonical schema)', () => {
  it('S1: panel renders placa input on mount', () => {
    mockUseCotizacion.mockReturnValue({ data: undefined, error: undefined, refresh: vi.fn() });
    render(<SalidaPanel uuid_ingreso={null} onPagoSubmit={vi.fn()} />);
    expect(screen.getByTestId('salida-panel')).toBeInTheDocument();
    expect(screen.getByTestId('salida-placa')).toBeInTheDocument();
  });

  it('S2: idle mode — uuid_ingreso=null → useCotizacion key=null (no fetch)', () => {
    mockUseCotizacion.mockReturnValue({ data: undefined, error: undefined, refresh: vi.fn() });
    render(<SalidaPanel uuid_ingreso={null} onPagoSubmit={vi.fn()} />);
    expect(mockUseCotizacion).toHaveBeenCalledWith(null);
  });

  it('S3: cotización rotación → <CotizacionPanel /> con <dl> + formatCOP value', () => {
    mockUseCotizacion.mockReturnValue({
      data: cotizacionRotacion,
      error: undefined,
      refresh: vi.fn(),
    });
    render(
      <SalidaPanel
        uuid_ingreso={UUID_INGRESO_A}
        onPagoSubmit={vi.fn()}
      />,
    );
    expect(screen.getByTestId('cotizacion-dl')).toBeInTheDocument();
    // formatCOP(48790) → "$ 48.790" (es-CO, no decimals).
    expect(screen.getByTestId('cotizacion-dl').textContent).toContain('48.790');
  });

  it('S4: clicking "Confirmar salida" abre el drawer pago via store (REQ-OPS-138)', () => {
    mockUseCotizacion.mockReturnValue({
      data: cotizacionRotacion,
      error: undefined,
      refresh: vi.fn(),
    });
    render(
      <SalidaPanel
        uuid_ingreso={UUID_INGRESO_B}
        onPagoSubmit={vi.fn()}
      />,
    );
    expect(useDashboardDrawerStore.getState().openDrawer).toBeNull();
    fireEvent.click(screen.getByTestId('cotizacion-confirmar'));
    expect(useDashboardDrawerStore.getState().openDrawer).toBe('pago');
  });

  it('S5: mensualidad (cobrar:false) renderiza banner, NO <dl>', () => {
    mockUseCotizacion.mockReturnValue({
      data: cotizacionMensualidad,
      error: undefined,
      refresh: vi.fn(),
    });
    render(
      <SalidaPanel
        uuid_ingreso={UUID_INGRESO_A}
        onPagoSubmit={vi.fn()}
      />,
    );
    expect(screen.getByTestId('cotizacion-mensualidad-banner')).toBeInTheDocument();
    expect(screen.queryByTestId('cotizacion-dl')).not.toBeInTheDocument();
  });
});
