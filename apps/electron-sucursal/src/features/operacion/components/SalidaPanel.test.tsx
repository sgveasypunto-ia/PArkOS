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
 *
 * HU-F7.1 (búsqueda sin placa) — autocomplete inside the panel's own
 * `salida-placa` field, T5:
 *   S6: `initialUuidIngreso` prop + estado-guard resolves `abierto` →
 *       `useCotizacion` is eventually invoked with that uuid.
 *   S7: `initialUuidIngreso` prop + estado-guard resolves `cerrado` →
 *       renders the "ya tiene salida" card; `useCotizacion` is never
 *       invoked with that uuid.
 *   S8: typing a partial placa renders a suggestion; selecting it (has
 *       placa) fills the form and reuses `handlePlacaSubmit` (tolerant
 *       search + estado-guard) — `useCotizacion` ends up called with
 *       the resolved uuid.
 *   S9: typing a partial consecutivo renders a suggestion; selecting
 *       it (no placa) runs the estado-guard directly (no tolerant
 *       placa search) — `useCotizacion` ends up called with the
 *       resolved uuid.
 *   S10: the `salida-placa` input exposes the WAI-ARIA combobox
 *        attributes wired to the shared listbox.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Named type-only imports so the `vi.mock` factories below can reference
// `typeof <Module>` instead of an inline `import()` type query
// (`@typescript-eslint/consistent-type-imports` forbids the latter).
import type * as UseCotizacionModule from '../hooks/useCotizacion';
import type * as UseRegistrarSalidaModule from '../hooks/useRegistrarSalida';
import type * as UiKitHooksModule from '@parkos/ui-kit/hooks';
import type * as IngresoActivoApiModule from '../api/ingresoActivoApi';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const mockUseCotizacion = vi.fn();
const mockUseRegistrarSalida = vi.fn();
vi.mock('../hooks/useCotizacion', async (importOriginal) => {
  const actual = await importOriginal<typeof UseCotizacionModule>();
  return {
    ...actual,
    useCotizacion: (...args: unknown[]) => mockUseCotizacion(...args),
  };
});
vi.mock('../hooks/useRegistrarSalida', async (importOriginal) => {
  const actual = await importOriginal<typeof UseRegistrarSalidaModule>();
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

// HU-F7.1 (T5) — autocomplete deps: sucursal (useAuth), live active-ingresos
// snapshot (useIngresosActivos), and the tolerant-search / estado-guard
// primitives (getIngresosByPlaca / getIngresoEstado).
const mockUseAuth = vi.fn();
vi.mock('@parkos/ui-kit/hooks', async (importOriginal) => {
  const actual = await importOriginal<typeof UiKitHooksModule>();
  return {
    ...actual,
    useAuth: () => mockUseAuth(),
  };
});

const mockUseIngresosActivos = vi.fn();
vi.mock('../hooks/useIngresosActivos', () => ({
  useIngresosActivos: (...args: unknown[]) => mockUseIngresosActivos(...args),
}));

const mockGetIngresosByPlaca = vi.fn();
const mockGetIngresoEstado = vi.fn();
vi.mock('../api/ingresoActivoApi', async (importOriginal) => {
  const actual = await importOriginal<typeof IngresoActivoApiModule>();
  return {
    ...actual,
    getIngresosByPlaca: (...args: unknown[]) => mockGetIngresosByPlaca(...args),
    getIngresoEstado: (...args: unknown[]) => mockGetIngresoEstado(...args),
  };
});

import { useDashboardDrawerStore } from '@/store/dashboardDrawerStore';
import { SalidaPanel } from './SalidaPanel';

beforeEach(() => {
  useDashboardDrawerStore.getState().close();
  mockUseCotizacion.mockReset();
  mockUseRegistrarSalida.mockReset();
  mockUseAuth.mockReset();
  mockUseAuth.mockReturnValue({ sucursal: { uuid: 'suc-uuid-1' } });
  mockUseIngresosActivos.mockReset();
  mockUseIngresosActivos.mockReturnValue([]);
  mockGetIngresosByPlaca.mockReset();
  mockGetIngresoEstado.mockReset();
  mockGetIngresoEstado.mockResolvedValue({ uuid_ingreso: 'unused', estado: 'abierto' });
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

describe('<SalidaPanel /> — HU-F7.1 búsqueda sin placa (T5)', () => {
  it('S6: initialUuidIngreso + estado abierto → useCotizacion eventually called with that uuid', async () => {
    mockUseCotizacion.mockReturnValue({ data: undefined, error: undefined, refresh: vi.fn() });
    mockGetIngresoEstado.mockResolvedValue({ uuid_ingreso: UUID_INGRESO_A, estado: 'abierto' });

    render(<SalidaPanel uuid_ingreso={null} initialUuidIngreso={UUID_INGRESO_A} />);

    await waitFor(() => {
      expect(mockUseCotizacion).toHaveBeenCalledWith(UUID_INGRESO_A);
    });
  });

  it('S7: initialUuidIngreso + estado cerrado → "ya tiene salida" card; useCotizacion never called with that uuid', async () => {
    mockUseCotizacion.mockReturnValue({ data: undefined, error: undefined, refresh: vi.fn() });
    mockGetIngresoEstado.mockResolvedValue({ uuid_ingreso: UUID_INGRESO_A, estado: 'cerrado' });

    render(<SalidaPanel uuid_ingreso={null} initialUuidIngreso={UUID_INGRESO_A} />);

    expect(await screen.findByTestId('salida-ingreso-cerrado')).toBeInTheDocument();
    expect(mockUseCotizacion).not.toHaveBeenCalledWith(UUID_INGRESO_A);
  });

  it('S8: typing a partial placa suggests a match; selecting it (con placa) reuses handlePlacaSubmit', async () => {
    mockUseCotizacion.mockReturnValue({ data: undefined, error: undefined, refresh: vi.fn() });
    mockUseIngresosActivos.mockReturnValue([
      {
        uuid: UUID_INGRESO_A,
        placa: 'ABC123',
        fecha_ingreso: '2026-09-19T10:00:00Z',
        consecutivo: null,
        created_at: '2026-09-19T10:00:00Z',
        uuid_tipo_vehiculo: '00000000-0000-0000-0000-000000000001',
        uuid_sucursal: 'suc-uuid-1',
      },
    ]);
    mockGetIngresosByPlaca.mockResolvedValue([
      {
        uuid: UUID_INGRESO_A,
        uuid_sucursal: 'suc-uuid-1',
        placa: 'ABC123',
        fecha_ingreso: '2026-09-19T10:00:00Z',
        uuid_subscripcion_cliente: null,
      },
    ]);
    mockGetIngresoEstado.mockResolvedValue({ uuid_ingreso: UUID_INGRESO_A, estado: 'abierto' });

    render(<SalidaPanel uuid_ingreso={null} />);
    await userEvent.type(screen.getByTestId('salida-placa'), 'ABC');

    const option = await screen.findByRole('option', { name: /ABC123/ });
    await userEvent.click(option);

    await waitFor(() => {
      expect(mockGetIngresosByPlaca).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(mockUseCotizacion).toHaveBeenCalledWith(UUID_INGRESO_A);
    });
  });

  it('S9: typing a partial consecutivo suggests a match; selecting it (sin placa) runs the estado-guard directly', async () => {
    mockUseCotizacion.mockReturnValue({ data: undefined, error: undefined, refresh: vi.fn() });
    mockUseIngresosActivos.mockReturnValue([
      {
        uuid: UUID_INGRESO_B,
        placa: null,
        fecha_ingreso: '2026-09-19T10:00:00Z',
        consecutivo: 'PATINETA-000003-34a24bae',
        created_at: '2026-09-19T10:00:00Z',
        uuid_tipo_vehiculo: '00000000-0000-0000-0000-000000000001',
        uuid_sucursal: 'suc-uuid-1',
      },
    ]);
    mockGetIngresoEstado.mockResolvedValue({ uuid_ingreso: UUID_INGRESO_B, estado: 'abierto' });

    render(<SalidaPanel uuid_ingreso={null} />);
    await userEvent.type(screen.getByTestId('salida-placa'), 'PATIN');

    const option = await screen.findByRole('option', { name: /PATINETA-000003-34a24bae/ });
    await userEvent.click(option);

    expect(mockGetIngresosByPlaca).not.toHaveBeenCalled();
    await waitFor(() => {
      expect(mockGetIngresoEstado).toHaveBeenCalledWith(UUID_INGRESO_B);
    });
    await waitFor(() => {
      expect(mockUseCotizacion).toHaveBeenCalledWith(UUID_INGRESO_B);
    });
  });

  it('S10: salida-placa exposes WAI-ARIA combobox attributes wired to the shared listbox', async () => {
    mockUseCotizacion.mockReturnValue({ data: undefined, error: undefined, refresh: vi.fn() });
    mockUseIngresosActivos.mockReturnValue([
      {
        uuid: UUID_INGRESO_A,
        placa: 'ABC123',
        fecha_ingreso: '2026-09-19T10:00:00Z',
        consecutivo: null,
        created_at: '2026-09-19T10:00:00Z',
        uuid_tipo_vehiculo: '00000000-0000-0000-0000-000000000001',
        uuid_sucursal: 'suc-uuid-1',
      },
    ]);

    render(<SalidaPanel uuid_ingreso={null} />);
    const input = screen.getByTestId('salida-placa');
    expect(input).toHaveAttribute('role', 'combobox');
    expect(input).toHaveAttribute('aria-expanded', 'false');

    await userEvent.type(input, 'ABC');
    const listbox = await screen.findByRole('listbox');
    expect(input).toHaveAttribute('aria-expanded', 'true');
    expect(input).toHaveAttribute('aria-controls', listbox.id);
  });

  it('S11: Escape while suggestions are open stops propagation — must not reach a window-level Escape listener (regression: Dashboard.tsx global F1-F6/Esc hotkey handler was closing the whole Sheet)', async () => {
    mockUseCotizacion.mockReturnValue({ data: undefined, error: undefined, refresh: vi.fn() });
    mockUseIngresosActivos.mockReturnValue([
      {
        uuid: UUID_INGRESO_A,
        placa: 'ABC123',
        fecha_ingreso: '2026-09-19T10:00:00Z',
        consecutivo: null,
        created_at: '2026-09-19T10:00:00Z',
        uuid_tipo_vehiculo: '00000000-0000-0000-0000-000000000001',
        uuid_sucursal: 'suc-uuid-1',
      },
    ]);

    // Dashboard.tsx wires a global `window.addEventListener('keydown', ...)`
    // that closes ANY open drawer on Escape — a real, pre-existing,
    // app-wide hotkey convention that this test does NOT mock away, so
    // it exercises the ACTUAL bubbling mechanism that caused the bug
    // (found via live Chrome DevTools validation, not by the
    // component-only tests above, which never render a window listener).
    const windowEscapeSpy = vi.fn();
    window.addEventListener('keydown', windowEscapeSpy);

    render(<SalidaPanel uuid_ingreso={null} />);
    const input = screen.getByTestId('salida-placa');
    await userEvent.type(input, 'ABC');
    await screen.findByRole('listbox');
    // `userEvent.type` above already bubbled 3 (non-Escape) keydowns to
    // `window` — that is legitimate (F1-F6 must always reach Dashboard).
    // Reset the spy so the assertion below is scoped to the Escape
    // keydown only.
    windowEscapeSpy.mockClear();

    fireEvent.keyDown(input, { key: 'Escape', code: 'Escape', bubbles: true });

    expect(windowEscapeSpy).not.toHaveBeenCalled();
    expect(screen.queryByRole('listbox')).toBeNull();

    window.removeEventListener('keydown', windowEscapeSpy);
  });
});
