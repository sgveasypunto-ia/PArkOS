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
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const mockUseCotizacion = vi.fn();
const mockUseRegistrarSalida = vi.fn();
vi.mock('../hooks/useCotizacion', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../hooks/useCotizacion')>();
  return {
    ...actual,
    useCotizacion: (...args: unknown[]) => mockUseCotizacion(...args),
  };
});
vi.mock('../hooks/useRegistrarSalida', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../hooks/useRegistrarSalida')>();
  return {
    ...actual,
    useRegistrarSalida: () => {
      const result = mockUseRegistrarSalida();
      return {
        trigger: result.trigger,
        isMutating: false,
        error: undefined,
        data: undefined,
      };
    },
  };
});

import { useDashboardDrawerStore } from '@/store/dashboardDrawerStore';
import { SalidaPanel } from './SalidaPanel';

beforeEach(() => {
  useDashboardDrawerStore.getState().close();
  mockUseCotizacion.mockReset();
  mockUseRegistrarSalida.mockReset();
  mockUseRegistrarSalida.mockReturnValue({
    trigger: vi.fn().mockResolvedValue({
      uuid: '00000000-0000-0000-0000-0000000000c1',
      uuid_sucursal: '00000000-0000-0000-0000-0000000000c2',
      uuid_ingreso: UUID_INGRESO_A,
      fecha_salida: '2026-09-19T11:00:00Z',
      created_at: '2026-09-19T11:00:00Z',
      created_by: '00000000-0000-0000-0000-0000000000c3',
      sync_status: 'pending',
      sync_timestamp: null,
      sync_attempts: 0,
      tipo_salida: 'ROTACION',
      forzado_en_creacion: false,
      motivo_forzado: null,
      cotizacion_snapshot: null,
    }),
  });
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
    render(<SalidaPanel uuid_ingreso={null} />);
    expect(screen.getByTestId('salida-panel')).toBeInTheDocument();
    expect(screen.getByTestId('salida-placa')).toBeInTheDocument();
  });

  it('S2: idle mode — uuid_ingreso=null → useCotizacion key=null (no fetch)', () => {
    mockUseCotizacion.mockReturnValue({ data: undefined, error: undefined, refresh: vi.fn() });
    render(<SalidaPanel uuid_ingreso={null} />);
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
       
      />,
    );
    expect(screen.getByTestId('cotizacion-dl')).toBeInTheDocument();
    // formatCOP(48790) → "$ 48.790" (es-CO, no decimals).
    expect(screen.getByTestId('cotizacion-dl').textContent).toContain('48.790');
  });

  it('S4: clicking "Confirmar salida" → useRegistrarSalida.trigger → 201 ROTACION → abre pago drawer (REQ-OPS-138)', async () => {
    mockUseCotizacion.mockReturnValue({
      data: cotizacionRotacion,
      error: undefined,
      refresh: vi.fn(),
    });
    render(
      <SalidaPanel
        uuid_ingreso={UUID_INGRESO_B}
       
      />,
    );
    expect(useDashboardDrawerStore.getState().openDrawer).toBeNull();
    fireEvent.click(screen.getByTestId('cotizacion-confirmar'));
    // Allow the async trigger promise to resolve.
    await new Promise((r) => setTimeout(r, 10));
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
       
      />,
    );
    expect(screen.getByTestId('cotizacion-mensualidad-banner')).toBeInTheDocument();
    expect(screen.queryByTestId('cotizacion-dl')).not.toBeInTheDocument();
  });
});
