/**
 * Tests for `<SalidaPanel />` (F7.1+F7.2 dashboard section).
 *
 * Coverage:
 *   S1: panel renders title + plate input on mount.
 *   S2: idle mode (uuid_ingreso=null) — `useCotizacion` is NOT invoked
 *       (REQ-OPS-139 lazy-mount invariant).
 *   S3: submit placa triggers the cotizacion flow when uuid_ingreso is
 *       non-null; the breakdown `<dl>` renders.
 *   S4: clicking "Cobrar" opens the drawer via the store.
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

describe('<SalidaPanel /> — F7.1+F7.2 dashboard section', () => {
  it('S1: panel renders title + plate input on mount', () => {
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

  it('S3: cotizacion non-null → renders breakdown dl + cobrar button', () => {
    mockUseCotizacion.mockReturnValue({
      data: {
        uuid_ingreso: '00000000-0000-0000-0000-000000000001',
        uuid_tarifa_vigente: '00000000-0000-0000-0000-000000000002',
        minutos_transcurridos: 60,
        base_cop: 3000,
        fraccion_cop: 1500,
        total_cop: 4500,
        generado_en: '2026-09-17T10:00:00Z',
      },
      error: undefined,
      refresh: vi.fn(),
    });
    render(
      <SalidaPanel
        uuid_ingreso="00000000-0000-0000-0000-000000000001"
        onPagoSubmit={vi.fn()}
      />,
    );
    expect(screen.getByTestId('cotizacion-dl')).toBeInTheDocument();
    expect(screen.getByTestId('cotizacion-total').textContent).toContain('4.500');
  });

  it('S4: clicking "Cobrar" opens the pago drawer via store', () => {
    mockUseCotizacion.mockReturnValue({
      data: {
        uuid_ingreso: '00000000-0000-0000-0000-000000000003',
        uuid_tarifa_vigente: '00000000-0000-0000-0000-000000000004',
        minutos_transcurridos: 30,
        base_cop: 1500,
        fraccion_cop: 750,
        total_cop: 2250,
        generado_en: '2026-09-17T10:00:00Z',
      },
      error: undefined,
      refresh: vi.fn(),
    });
    render(
      <SalidaPanel
        uuid_ingreso="00000000-0000-0000-0000-000000000003"
        onPagoSubmit={vi.fn()}
      />,
    );
    expect(useDashboardDrawerStore.getState().openDrawer).toBeNull();
    fireEvent.click(screen.getByTestId('salida-cobrar'));
    expect(useDashboardDrawerStore.getState().openDrawer).toBe('pago');
  });
});