/**
 * Tests for `<SuscripcionesSheet />` — HU-F9.1 (venta) + HU-F9.2
 * realineada (listado + búsqueda por identificación + gestión de
 * cupos), REQ-OPS-138 single-drawer invariant.
 *
 * Coverage:
 *   S1: closed by default — renders nothing when openDrawer !== 'suscripciones'.
 *   S2: open → list mode shows the active-subscriptions list.
 *   S3: search submit with a match → advances to 'cupos' mode with the
 *       fetched detail rendered (plan, cupo, vehiculos).
 *   S4: search submit with no match → shows the empty-result message,
 *       stays in 'list' mode.
 *   S5: clicking a list row fetches that client's detail and advances
 *       to 'cupos' mode.
 *   S6: cupos mode — "Quitar" on a vehiculo calls the mutation and
 *       re-renders with the updated detalle + refreshes the list.
 *   S7: cupos mode — the agregar form calls the mutation with the
 *       typed placa and updates the detalle.
 *   S8: cupo lleno (cupo_disponible=0) hides the agregar form.
 *   S9: "Volver" returns to 'list' mode.
 *   S10: "+ Nueva venta" switches to 'venta' mode (embeds <Venta />).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (_ns: string, opts?: { defaultValue?: string }) => opts?.defaultValue ?? _ns }),
}));

const PERMISO = 'gestionar_placas_suscripcion';
const mockUseAuth = vi.fn((): { sucursal: { uuid: string }; permisos: string[] } => ({
  sucursal: { uuid: 'suc-1' },
  permisos: [PERMISO],
}));
vi.mock('@parkos/ui-kit/hooks', () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock('../pages/Venta', () => ({
  Venta: (props: { onSuccess?: () => void; onCancel?: () => void }) => (
    <div data-testid="venta-stub">
      <button type="button" onClick={props.onCancel} data-testid="venta-stub-cancel">
        cancel
      </button>
      <button type="button" onClick={props.onSuccess} data-testid="venta-stub-success">
        success
      </button>
    </div>
  ),
}));

const mockRefresh = vi.fn();
const mockListData = vi.fn();
vi.mock('../hooks/useSuscripcionesActivas', () => ({
  useSuscripcionesActivas: () => ({
    data: mockListData(),
    error: undefined,
    refresh: mockRefresh,
  }),
}));

const mockRenovablesData = vi.fn((): unknown[] | undefined => []);
const mockRefreshRenovables = vi.fn();
vi.mock('../hooks/useSuscripcionesRenovables', () => ({
  useSuscripcionesRenovables: () => ({
    data: mockRenovablesData(),
    error: undefined,
    refresh: mockRefreshRenovables,
  }),
}));

// The renewal panel has its own tests; here only the drawer navigation matters.
vi.mock('./RenovarSuscripcionPanel', () => ({
  RenovarSuscripcionPanel: (props: {
    target: { uuid: string; placas?: string[] };
    onBack: () => void;
    onRenovada: () => void;
  }) => (
    <div data-testid="renovar-stub" data-uuid={props.target.uuid}>
      <button type="button" onClick={props.onBack} data-testid="renovar-stub-volver">
        volver
      </button>
      <button type="button" onClick={props.onRenovada} data-testid="renovar-stub-ok">
        ok
      </button>
    </div>
  ),
}));

const mockBuscarTrigger = vi.fn();
const mockBuscarData = vi.fn(() => undefined as unknown);
vi.mock('../hooks/useBuscarSuscripcionPorIdentificacion', () => ({
  useBuscarSuscripcionPorIdentificacion: () => ({
    trigger: mockBuscarTrigger,
    isMutating: false,
    error: undefined,
    data: mockBuscarData(),
  }),
}));

const mockAgregarTrigger = vi.fn();
const mockAgregarError = vi.fn((): unknown => undefined);
vi.mock('../hooks/useAgregarVehiculoSuscripcion', () => ({
  useAgregarVehiculoSuscripcion: () => ({
    trigger: mockAgregarTrigger,
    isMutating: false,
    error: mockAgregarError(),
    data: undefined,
  }),
}));

const mockQuitarTrigger = vi.fn();
vi.mock('../hooks/useQuitarVehiculoSuscripcion', () => ({
  useQuitarVehiculoSuscripcion: () => ({
    trigger: mockQuitarTrigger,
    isMutating: false,
    error: undefined,
    data: undefined,
  }),
}));

import { useDashboardDrawerStore } from '@/store/dashboardDrawerStore';
import { SuscripcionesSheet } from './SuscripcionesSheet';

const LISTA = [
  {
    uuid: 'sub-1',
    cliente: { uuid: 'cli-1', nombre: 'Cupos', apellido: 'DeTest', numero_identificacion: '9998887771' },
    plan: { uuid: 'plan-1', tipo: 'MENSUAL_EMPRESA', valor: '800000', cantidad_maxima_vehiculos: 10, mismo_tipo_vehiculo: false },
    fecha_inicio_cobertura: '2026-09-24',
    fecha_vencimiento: '2026-10-24',
    cupo_maximo: 10,
    vehiculos_inscritos: 2,
  },
];

const DETALLE = {
  uuid: 'sub-1',
  cliente: { uuid: 'cli-1', nombre: 'Cupos', apellido: 'DeTest', numero_identificacion: '9998887771' },
  plan: { uuid: 'plan-1', tipo: 'MENSUAL_EMPRESA', valor: '800000', cantidad_maxima_vehiculos: 10, mismo_tipo_vehiculo: false },
  fecha_inicio_cobertura: '2026-09-24',
  fecha_vencimiento: '2026-10-24',
  cupo_maximo: 10,
  cupo_disponible: 8,
  vehiculos: [
    { uuid: 'sv-1', uuid_vehiculo: 'v-1', placa: 'CUP001' },
    { uuid: 'sv-2', uuid_vehiculo: 'v-2', placa: 'CUP002' },
  ],
};

beforeEach(() => {
  cleanup();
  useDashboardDrawerStore.getState().close();
  mockListData.mockReturnValue(LISTA);
  mockBuscarData.mockReturnValue(undefined);
  mockBuscarTrigger.mockReset();
  mockAgregarTrigger.mockReset();
  mockQuitarTrigger.mockReset();
  mockRefresh.mockReset();
  mockRefreshRenovables.mockReset();
  mockRenovablesData.mockReturnValue([]);
  mockAgregarError.mockReturnValue(undefined);
  mockUseAuth.mockReturnValue({ sucursal: { uuid: 'suc-1' }, permisos: [PERMISO] });
});

describe('<SuscripcionesSheet /> — HU-F9.1 + HU-F9.2 realineada', () => {
  it('S1: closed by default — renders nothing', () => {
    const { container } = render(<SuscripcionesSheet />);
    expect(container.firstChild).toBeNull();
  });

  it('S2: open → list mode shows the active-subscriptions list', () => {
    useDashboardDrawerStore.getState().open('suscripciones', 'sidebar-suscripciones');
    render(<SuscripcionesSheet />);
    expect(screen.getByTestId('suscripciones-sheet-list')).toBeInTheDocument();
    expect(screen.getByTestId('suscripciones-sheet-item-sub-1')).toHaveTextContent('Cupos DeTest');
    expect(screen.getByTestId('suscripciones-sheet-cupo-sub-1')).toHaveTextContent('2/10');
  });

  it('S3: search submit with a match → advances to cupos mode with the detail', async () => {
    mockBuscarTrigger.mockResolvedValue(DETALLE);
    useDashboardDrawerStore.getState().open('suscripciones', 'sidebar-suscripciones');
    render(<SuscripcionesSheet />);

    const user = userEvent.setup();
    await user.type(screen.getByTestId('suscripciones-buscar-input'), '9998887771');
    await user.click(screen.getByTestId('suscripciones-buscar-submit'));

    expect(mockBuscarTrigger).toHaveBeenCalledWith('9998887771');
    await waitFor(() => {
      expect(screen.getByTestId('suscripciones-cupos-detalle')).toBeInTheDocument();
    });
    expect(screen.getByTestId('suscripciones-cupos-resumen')).toHaveTextContent('2/10');
    expect(screen.getByTestId('suscripciones-cupos-vehiculo-sv-1')).toHaveTextContent('CUP001');
  });

  it('S4: search submit with no match → shows empty-result message, stays in list', async () => {
    mockBuscarTrigger.mockResolvedValue(null);
    mockBuscarData.mockReturnValue(null);
    useDashboardDrawerStore.getState().open('suscripciones', 'sidebar-suscripciones');
    render(<SuscripcionesSheet />);

    const user = userEvent.setup();
    await user.type(screen.getByTestId('suscripciones-buscar-input'), '000000');
    await user.click(screen.getByTestId('suscripciones-buscar-submit'));

    await waitFor(() => {
      expect(screen.getByTestId('suscripciones-buscar-sin-resultado')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('suscripciones-cupos-detalle')).not.toBeInTheDocument();
  });

  describe('búsqueda por nombre (defecto 7.5)', () => {
    const mk = (uuid: string, nombre: string, apellido: string, id: string) => ({
      ...LISTA[0],
      uuid,
      cliente: { uuid: `cli-${uuid}`, nombre, apellido, numero_identificacion: id },
    });
    const VARIOS = [
      mk('a', 'Juan', 'Pérez', '1001'),
      mk('b', 'Juan Carlos', 'Gómez', '1002'),
      mk('c', 'José', 'Núñez', '1003'),
    ];

    it('S7: escribir "juan" filtra la lista por nombre (case-insensitive)', async () => {
      mockListData.mockReturnValue(VARIOS);
      useDashboardDrawerStore.getState().open('suscripciones', 'sidebar-suscripciones');
      render(<SuscripcionesSheet />);
      const user = userEvent.setup();
      await user.type(screen.getByTestId('suscripciones-buscar-input'), 'JUAN');
      expect(screen.getByTestId('suscripciones-sheet-item-a')).toBeInTheDocument();
      expect(screen.getByTestId('suscripciones-sheet-item-b')).toBeInTheDocument();
      expect(screen.queryByTestId('suscripciones-sheet-item-c')).toBeNull();
    });

    it('S8: tolera acentos ("jose" encuentra "José"; "nunez" encuentra "Núñez")', async () => {
      mockListData.mockReturnValue(VARIOS);
      useDashboardDrawerStore.getState().open('suscripciones', 'sidebar-suscripciones');
      render(<SuscripcionesSheet />);
      const user = userEvent.setup();
      await user.type(screen.getByTestId('suscripciones-buscar-input'), 'jose');
      expect(screen.getByTestId('suscripciones-sheet-item-c')).toBeInTheDocument();
      expect(screen.queryByTestId('suscripciones-sheet-item-a')).toBeNull();
    });

    it('S9: submit con varias coincidencias por nombre NO consulta; deja elegir de la lista', async () => {
      mockListData.mockReturnValue(VARIOS);
      useDashboardDrawerStore.getState().open('suscripciones', 'sidebar-suscripciones');
      render(<SuscripcionesSheet />);
      const user = userEvent.setup();
      await user.type(screen.getByTestId('suscripciones-buscar-input'), 'juan');
      await user.click(screen.getByTestId('suscripciones-buscar-submit'));
      expect(mockBuscarTrigger).not.toHaveBeenCalled();
      expect(screen.getByTestId('suscripciones-sheet-item-a')).toBeInTheDocument();
    });

    it('S10: submit con UNA coincidencia por nombre abre sus cupos por su identificación', async () => {
      mockListData.mockReturnValue(VARIOS);
      mockBuscarTrigger.mockResolvedValue(DETALLE);
      useDashboardDrawerStore.getState().open('suscripciones', 'sidebar-suscripciones');
      render(<SuscripcionesSheet />);
      const user = userEvent.setup();
      await user.type(screen.getByTestId('suscripciones-buscar-input'), 'jos');
      await user.click(screen.getByTestId('suscripciones-buscar-submit'));
      expect(mockBuscarTrigger).toHaveBeenCalledWith('1003');
      await waitFor(() => {
        expect(screen.getByTestId('suscripciones-cupos-detalle')).toBeInTheDocument();
      });
    });

    it('S11: sin coincidencias en la lista, submit conserva la búsqueda exacta por identificación', async () => {
      mockListData.mockReturnValue(VARIOS);
      mockBuscarTrigger.mockResolvedValue(null);
      useDashboardDrawerStore.getState().open('suscripciones', 'sidebar-suscripciones');
      render(<SuscripcionesSheet />);
      const user = userEvent.setup();
      await user.type(screen.getByTestId('suscripciones-buscar-input'), '777');
      await user.click(screen.getByTestId('suscripciones-buscar-submit'));
      expect(mockBuscarTrigger).toHaveBeenCalledWith('777');
    });
  });

  it('S5: clicking a list row fetches the detail and advances to cupos mode', async () => {
    mockBuscarTrigger.mockResolvedValue(DETALLE);
    useDashboardDrawerStore.getState().open('suscripciones', 'sidebar-suscripciones');
    render(<SuscripcionesSheet />);

    const user = userEvent.setup();
    await user.click(screen.getByTestId('suscripciones-sheet-item-sub-1'));

    expect(mockBuscarTrigger).toHaveBeenCalledWith('9998887771');
    await waitFor(() => {
      expect(screen.getByTestId('suscripciones-cupos-detalle')).toBeInTheDocument();
    });
  });

  it('S6: quitar calls the mutation, updates the detalle, refreshes the list', async () => {
    mockBuscarTrigger.mockResolvedValue(DETALLE);
    const actualizado = { ...DETALLE, cupo_disponible: 9, vehiculos: [DETALLE.vehiculos[1]] };
    mockQuitarTrigger.mockResolvedValue(actualizado);
    useDashboardDrawerStore.getState().open('suscripciones', 'sidebar-suscripciones');
    render(<SuscripcionesSheet />);

    const user = userEvent.setup();
    await user.click(screen.getByTestId('suscripciones-sheet-item-sub-1'));
    await waitFor(() => screen.getByTestId('suscripciones-cupos-detalle'));

    await user.click(screen.getByTestId('suscripciones-cupos-quitar-sv-1'));

    expect(mockQuitarTrigger).toHaveBeenCalledWith('sv-1');
    await waitFor(() => {
      expect(screen.queryByTestId('suscripciones-cupos-vehiculo-sv-1')).not.toBeInTheDocument();
    });
    expect(screen.getByTestId('suscripciones-cupos-resumen')).toHaveTextContent('1/10');
    expect(mockRefresh).toHaveBeenCalled();
  });

  it('S7: agregar form submits the typed placa and updates the detalle', async () => {
    mockBuscarTrigger.mockResolvedValue(DETALLE);
    const actualizado = {
      ...DETALLE,
      cupo_disponible: 7,
      vehiculos: [...DETALLE.vehiculos, { uuid: 'sv-3', uuid_vehiculo: 'v-3', placa: 'CUP003' }],
    };
    mockAgregarTrigger.mockResolvedValue(actualizado);
    useDashboardDrawerStore.getState().open('suscripciones', 'sidebar-suscripciones');
    render(<SuscripcionesSheet />);

    const user = userEvent.setup();
    await user.click(screen.getByTestId('suscripciones-sheet-item-sub-1'));
    await waitFor(() => screen.getByTestId('suscripciones-cupos-detalle'));

    await user.type(screen.getByTestId('suscripciones-cupos-agregar-input'), 'CUP003');
    await user.click(screen.getByTestId('suscripciones-cupos-agregar-submit'));

    expect(mockAgregarTrigger).toHaveBeenCalledWith({
      uuid_subscripcion_cliente: 'sub-1',
      placa: 'CUP003',
    });
    await waitFor(() => {
      expect(screen.getByTestId('suscripciones-cupos-vehiculo-sv-3')).toBeInTheDocument();
    });
  });

  it('S8: cupo lleno hides the agregar form', async () => {
    mockBuscarTrigger.mockResolvedValue({ ...DETALLE, cupo_disponible: 0 });
    useDashboardDrawerStore.getState().open('suscripciones', 'sidebar-suscripciones');
    render(<SuscripcionesSheet />);

    const user = userEvent.setup();
    await user.click(screen.getByTestId('suscripciones-sheet-item-sub-1'));
    await waitFor(() => screen.getByTestId('suscripciones-cupos-detalle'));

    expect(screen.getByTestId('suscripciones-cupos-lleno')).toBeInTheDocument();
    expect(screen.queryByTestId('suscripciones-cupos-agregar-form')).not.toBeInTheDocument();
  });

  it('S9: Volver returns to list mode', async () => {
    mockBuscarTrigger.mockResolvedValue(DETALLE);
    useDashboardDrawerStore.getState().open('suscripciones', 'sidebar-suscripciones');
    render(<SuscripcionesSheet />);

    const user = userEvent.setup();
    await user.click(screen.getByTestId('suscripciones-sheet-item-sub-1'));
    await waitFor(() => screen.getByTestId('suscripciones-cupos-detalle'));

    await user.click(screen.getByTestId('suscripciones-cupos-volver'));

    expect(screen.getByTestId('suscripciones-sheet-list')).toBeInTheDocument();
    expect(screen.queryByTestId('suscripciones-cupos-detalle')).not.toBeInTheDocument();
  });

  it('S10: "+ Nueva venta" switches to venta mode', async () => {
    useDashboardDrawerStore.getState().open('suscripciones', 'sidebar-suscripciones');
    render(<SuscripcionesSheet />);

    const user = userEvent.setup();
    await user.click(screen.getByTestId('suscripciones-sheet-nueva-venta'));

    expect(screen.getByTestId('venta-stub')).toBeInTheDocument();
  });

  it('S10b (PT-1): the wizard\'s step-1 "Volver" (onCancel) lands on the list', async () => {
    useDashboardDrawerStore.getState().open('suscripciones', 'sidebar-suscripciones');
    render(<SuscripcionesSheet />);

    const user = userEvent.setup();
    await user.click(screen.getByTestId('suscripciones-sheet-nueva-venta'));
    await user.click(screen.getByTestId('venta-stub-cancel'));

    expect(screen.getByTestId('suscripciones-sheet-list')).toBeInTheDocument();
    expect(screen.queryByTestId('venta-stub')).not.toBeInTheDocument();
  });

  it('S11 (PT-2): an operator without the permission sees NO Agregar/Quitar', async () => {
    mockUseAuth.mockReturnValue({ sucursal: { uuid: 'suc-1' }, permisos: [] });
    mockBuscarTrigger.mockResolvedValue(DETALLE);
    useDashboardDrawerStore.getState().open('suscripciones', 'sidebar-suscripciones');
    render(<SuscripcionesSheet />);

    const user = userEvent.setup();
    await user.click(screen.getByTestId('suscripciones-sheet-item-sub-1'));
    await waitFor(() => screen.getByTestId('suscripciones-cupos-detalle'));

    expect(screen.getByTestId('suscripciones-cupos-vehiculo-sv-1')).toHaveTextContent('CUP001');
    expect(screen.queryByTestId('suscripciones-cupos-quitar-sv-1')).not.toBeInTheDocument();
    expect(screen.queryByTestId('suscripciones-cupos-agregar-form')).not.toBeInTheDocument();
    expect(screen.getByTestId('suscripciones-cupos-solo-supervisor')).toBeInTheDocument();
  });

  it('S12 (PT-2): a supervisor sees them and backend errors render as Spanish messages', async () => {
    const { CuposPlacaConSuscripcionActivaError } = await import('../hooks/cuposErrors');
    mockAgregarError.mockReturnValue(new CuposPlacaConSuscripcionActivaError('ZZZ999', 'sub-9'));
    mockBuscarTrigger.mockResolvedValue(DETALLE);
    useDashboardDrawerStore.getState().open('suscripciones', 'sidebar-suscripciones');
    render(<SuscripcionesSheet />);

    const user = userEvent.setup();
    await user.click(screen.getByTestId('suscripciones-sheet-item-sub-1'));
    await waitFor(() => screen.getByTestId('suscripciones-cupos-detalle'));

    expect(screen.getByTestId('suscripciones-cupos-quitar-sv-1')).toBeInTheDocument();
    expect(screen.getByTestId('suscripciones-cupos-agregar-form')).toBeInTheDocument();
    const err = screen.getByTestId('suscripciones-cupos-agregar-error');
    expect(err).toHaveTextContent('ZZZ999');
    expect(err).toHaveTextContent('otra suscripción activa');
    expect(err).not.toHaveTextContent('placa_con_suscripcion_activa');
  });

  const RENOVABLE = {
    uuid: 'sub-1',
    cliente_nombre: 'Cupos DeTest',
    plan_nombre: 'MENSUAL_EMPRESA',
    placas: ['CUP001', 'CUP002'],
    fecha_vencimiento: '2026-10-08',
    dias_restantes: 3,
    dias_alerta_pre_vencimiento: 7,
    puede_renovar: true,
  };

  it('S13 (PT-3): "Renovar" appears only for renewable subscriptions', () => {
    mockRenovablesData.mockReturnValue([RENOVABLE]);
    useDashboardDrawerStore.getState().open('suscripciones', 'sidebar-suscripciones');
    render(<SuscripcionesSheet />);
    expect(screen.getByTestId('suscripciones-renovar-sub-1')).toBeInTheDocument();
  });

  it('S13c (UX3): the section states its criterion (<= 10 days or expired), not just "Por renovar"', () => {
    mockRenovablesData.mockReturnValue([RENOVABLE]);
    useDashboardDrawerStore.getState().open('suscripciones', 'sidebar-suscripciones');
    render(<SuscripcionesSheet />);
    expect(screen.getByTestId('suscripciones-renovables-criterio')).toHaveTextContent(
      'vencen en 10 días o menos, o ya vencieron',
    );
  });

  it('S13b (PT-3): nothing renewable -> no "Por renovar" section nor Renovar button', () => {
    useDashboardDrawerStore.getState().open('suscripciones', 'sidebar-suscripciones');
    render(<SuscripcionesSheet />);
    expect(screen.queryByTestId('suscripciones-renovables')).not.toBeInTheDocument();
    expect(screen.queryByTestId('suscripciones-renovar-sub-1')).not.toBeInTheDocument();
  });

  it('S14 (PT-1/PT-3): renew from the list -> "Volver" returns to the list', async () => {
    mockRenovablesData.mockReturnValue([RENOVABLE]);
    useDashboardDrawerStore.getState().open('suscripciones', 'sidebar-suscripciones');
    render(<SuscripcionesSheet />);

    const user = userEvent.setup();
    await user.click(screen.getByTestId('suscripciones-renovar-sub-1'));
    expect(screen.getByTestId('renovar-stub')).toHaveAttribute('data-uuid', 'sub-1');

    await user.click(screen.getByTestId('renovar-stub-volver'));
    expect(screen.getByTestId('suscripciones-sheet-list')).toBeInTheDocument();
    expect(screen.queryByTestId('renovar-stub')).not.toBeInTheDocument();
  });

  it('S15 (PT-1/PT-3): renew from the cupos detail -> "Volver" returns to that detail; only if puede_renovar', async () => {
    mockBuscarTrigger.mockResolvedValue({ ...DETALLE, dias_restantes: 5, puede_renovar: true });
    useDashboardDrawerStore.getState().open('suscripciones', 'sidebar-suscripciones');
    render(<SuscripcionesSheet />);

    const user = userEvent.setup();
    await user.click(screen.getByTestId('suscripciones-sheet-item-sub-1'));
    await waitFor(() => screen.getByTestId('suscripciones-cupos-detalle'));
    await user.click(screen.getByTestId('suscripciones-cupos-renovar'));
    expect(screen.getByTestId('renovar-stub')).toBeInTheDocument();

    await user.click(screen.getByTestId('renovar-stub-volver'));
    expect(screen.getByTestId('suscripciones-cupos-detalle')).toBeInTheDocument();
    expect(screen.getByTestId('suscripciones-cupos-vehiculo-sv-1')).toHaveTextContent('CUP001');
  });

  it('S15b: cupos detail with 25 days left still offers "Renovar" (no anticipation window)', async () => {
    mockBuscarTrigger.mockResolvedValue({ ...DETALLE, dias_restantes: 25, puede_renovar: true });
    useDashboardDrawerStore.getState().open('suscripciones', 'sidebar-suscripciones');
    render(<SuscripcionesSheet />);

    const user = userEvent.setup();
    await user.click(screen.getByTestId('suscripciones-sheet-item-sub-1'));
    await waitFor(() => screen.getByTestId('suscripciones-cupos-detalle'));
    expect(screen.getByTestId('suscripciones-cupos-renovar')).toBeInTheDocument();
  });

  it('S15c: the "Por renovar" badge only marks urgent rows (<= 10 days), not every renewable one', () => {
    mockListData.mockReturnValue([
      { ...LISTA[0], uuid: 'sub-lejos', dias_restantes: 25, puede_renovar: true },
      { ...LISTA[0], uuid: 'sub-cerca', dias_restantes: 4, puede_renovar: true },
    ]);
    useDashboardDrawerStore.getState().open('suscripciones', 'sidebar-suscripciones');
    render(<SuscripcionesSheet />);
    expect(screen.queryByTestId('suscripciones-sheet-por-renovar-sub-lejos')).not.toBeInTheDocument();
    expect(screen.getByTestId('suscripciones-sheet-por-renovar-sub-cerca')).toBeInTheDocument();
  });

  it('S16 (PT-3): after a renewal the lists are refreshed and the list is shown', async () => {
    mockRenovablesData.mockReturnValue([RENOVABLE]);
    useDashboardDrawerStore.getState().open('suscripciones', 'sidebar-suscripciones');
    render(<SuscripcionesSheet />);

    const user = userEvent.setup();
    await user.click(screen.getByTestId('suscripciones-renovar-sub-1'));
    await user.click(screen.getByTestId('renovar-stub-ok'));

    expect(mockRefresh).toHaveBeenCalled();
    expect(mockRefreshRenovables).toHaveBeenCalled();
    expect(screen.getByTestId('suscripciones-sheet-list')).toBeInTheDocument();
  });
});
