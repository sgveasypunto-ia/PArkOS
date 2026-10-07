/**
 * `SuscripcionForm.test.tsx` — HU-F20.2 crear/editar suscripción.
 *
 * Covers: the "sin sucursal" guard (CREATE mode only), the prorrateo
 * panel (BR2), vehiculo-level error mapping (409
 * `placa_con_suscripcion_activa` -- PT-2; legacy 422
 * `placa_con_suscripcion_vigente` kept as an alias -- plus the other
 * contract codes) surfaced inline without blocking the already-saved
 * subscripcion, plan <-> vehicle-type filtering and validation (PT-2), and
 * the EDIT-mode defaults.
 */
import { createElement } from 'react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type * as ClientesApiModule from '../api/clientesApi';

import { SUCURSAL_STORAGE_KEY, SucursalProvider } from '@/lib/sucursal-context';

const { PLAN, PLAN_CARRO, PLAN_MOTO, VIGENTE, TIPO_CARRO, TIPO_MOTO } = vi.hoisted(() => {
  const TIPO_CARRO = '44444444-4444-4444-4444-444444444444';
  const TIPO_MOTO = '55555555-5555-5555-5555-555555555555';
  const base = {
    vigente_desde: '2026-01-01T00:00:00',
    vigente_hasta: null,
    estado: 'activo',
    valor: 30000,
    duracion_dias: 30,
    cantidad_maxima_vehiculos: 2,
    mismo_tipo_vehiculo: false,
  };
  return {
    TIPO_CARRO,
    TIPO_MOTO,
    PLAN: {
      ...base,
      uuid: '33333333-3333-3333-3333-333333333333',
      tipo: 'Mensual cualquiera',
      uuid_tipo_vehiculo: null,
    },
    PLAN_CARRO: {
      ...base,
      uuid: '66666666-6666-6666-6666-666666666666',
      tipo: 'Mensual carro',
      uuid_tipo_vehiculo: TIPO_CARRO,
    },
    PLAN_MOTO: {
      ...base,
      uuid: '77777777-7777-7777-7777-777777777777',
      tipo: 'Mensual moto',
      uuid_tipo_vehiculo: TIPO_MOTO,
    },
    VIGENTE: {
      uuid: 'sub-1',
      uuid_cliente: 'cliente-1',
      uuid_sucursal: 'suc-1',
      uuid_tipo_subscripcion: '33333333-3333-3333-3333-333333333333',
      fecha_inicio_cobertura: '2026-01-01',
      fecha_vencimiento: '2026-12-31',
      dias_alerta_pre_vencimiento: 15,
      vigente_desde: '2026-01-01T00:00:00',
      vigente_hasta: null,
      estado: 'activo',
      created_at: '2026-01-01T00:00:00',
      created_by: null,
      sync_status: null,
    },
  };
});

const mockCreateSubscripcionVehiculo = vi.fn();
const mockListVehiculos = vi.fn();
const mockValidarAlta = vi.fn();

vi.mock('../api/clientesApi', async () => {
  const actual = await vi.importActual<typeof ClientesApiModule>('../api/clientesApi');
  return {
    ...actual,
    createSubscripcionVehiculo: (...args: unknown[]) => mockCreateSubscripcionVehiculo(...args),
    listVehiculos: (...args: unknown[]) => mockListVehiculos(...args),
    validarAltaSubscripcion: (...args: unknown[]) => mockValidarAlta(...args),
  };
});

vi.mock('@/features/catalogos/api/catalogApi', () => ({
  listCatalog: vi.fn().mockResolvedValue([PLAN, PLAN_CARRO, PLAN_MOTO]),
}));

import { ClientesApiError } from '../api/clientesApi';
import { SuscripcionForm } from './SuscripcionForm';

function wrapper({ children }: { children: ReactNode }): JSX.Element {
  return createElement(SucursalProvider, null, children);
}

function apiError(status: number, detail: Record<string, unknown>): ClientesApiError {
  const body = JSON.stringify({ detail });
  return new ClientesApiError(`clientesApi: POST /x -> ${status}: ${body}`, status, body);
}

beforeEach(() => {
  window.localStorage.removeItem(SUCURSAL_STORAGE_KEY);
  mockCreateSubscripcionVehiculo.mockReset();
  mockListVehiculos.mockReset();
  mockValidarAlta.mockReset();
  mockValidarAlta.mockResolvedValue(undefined);
  mockListVehiculos.mockResolvedValue({
    items: [
      { uuid: 'veh-1', placa: 'ABC123', uuid_tipo_vehiculo: TIPO_CARRO, estado: 'activo' },
      { uuid: 'veh-2', placa: 'XYZ98A', uuid_tipo_vehiculo: TIPO_MOTO, estado: 'activo' },
    ],
    next_cursor: null,
  });
});

async function renderCreate(onSubmit = vi.fn(), onDone = vi.fn()) {
  window.localStorage.setItem(SUCURSAL_STORAGE_KEY, 'suc-1');
  render(<SuscripcionForm onSubmit={onSubmit} onDone={onDone} onCancel={vi.fn()} />, { wrapper });
  await waitFor(() => {
    expect(screen.getByTestId('suscripcion-field-plan')).toBeInTheDocument();
  });
  // Wait until vehicles + plans have loaded.
  await waitFor(() => {
    expect(
      (screen.getByTestId('suscripcion-field-plan') as HTMLSelectElement).options.length,
    ).toBeGreaterThan(1);
  });
  return { onSubmit, onDone };
}

async function addVehiculo(index: number, uuid: string): Promise<void> {
  await userEvent.click(screen.getByTestId('suscripcion-agregar-vehiculo'));
  await waitFor(() => {
    expect(screen.getByTestId(`suscripcion-vehiculo-select-${index}`)).toBeInTheDocument();
  });
  await waitFor(() => {
    expect(
      (screen.getByTestId(`suscripcion-vehiculo-select-${index}`) as HTMLSelectElement).options
        .length,
    ).toBeGreaterThan(1);
  });
  await userEvent.selectOptions(screen.getByTestId(`suscripcion-vehiculo-select-${index}`), uuid);
}

function planOptionLabels(): string[] {
  return Array.from(
    (screen.getByTestId('suscripcion-field-plan') as HTMLSelectElement).options,
  ).map((o) => o.textContent ?? '');
}

describe('<SuscripcionForm /> -- crear', () => {
  it('disables submit and shows a guard when no sucursal is selected', async () => {
    const onSubmit = vi.fn();
    render(<SuscripcionForm onSubmit={onSubmit} onDone={vi.fn()} onCancel={vi.fn()} />, {
      wrapper,
    });

    await waitFor(() => {
      expect(screen.getByTestId('suscripcion-form-sin-sucursal')).toBeInTheDocument();
    });
    expect(screen.getByTestId('suscripcion-form-submit')).toBeDisabled();
  });

  it('shows the FULL plan valor in the monto panel once a plan is set (no proration)', async () => {
    await renderCreate();
    await userEvent.selectOptions(
      screen.getByTestId('suscripcion-field-plan'),
      '33333333-3333-3333-3333-333333333333',
    );

    await waitFor(() => {
      const text = screen.getByTestId('suscripcion-monto-referencia').textContent ?? '';
      expect(text).not.toMatch(/Seleccioná un plan/);
      expect(text.replace(/\D/g, '')).toContain('30000');
    });
    // Whatever the start date (here: last day of a month), the amount is the full plan.
    await userEvent.clear(screen.getByTestId('suscripcion-field-fecha-inicio'));
    await userEvent.type(screen.getByTestId('suscripcion-field-fecha-inicio'), '2026-09-30');
    await waitFor(() => {
      const text = screen.getByTestId('suscripcion-monto-referencia').textContent ?? '';
      expect(text.replace(/\D/g, '')).toContain('30000');
    });
  });

  it('suggests fecha_vencimiento = inicio + duracion - 1 (plan of N days covers exactly N days)', async () => {
    await renderCreate();
    await userEvent.selectOptions(
      screen.getByTestId('suscripcion-field-plan'),
      '33333333-3333-3333-3333-333333333333',
    );
    await userEvent.clear(screen.getByTestId('suscripcion-field-fecha-inicio'));
    await userEvent.type(screen.getByTestId('suscripcion-field-fecha-inicio'), '2026-09-01');
    // PLAN has duracion_dias = 30: Sep 1 + 29 = Sep 30.
    await waitFor(() => {
      expect(screen.getByTestId('suscripcion-field-fecha-vencimiento')).toHaveValue('2026-09-30');
    });
  });

  it('maps the 409 placa_con_suscripcion_activa to a readable message naming the plate, without losing the saved subscripcion', async () => {
    const onSubmit = vi.fn().mockResolvedValue({ ...VIGENTE, uuid: 'sub-new' });
    const onDone = vi.fn();
    mockCreateSubscripcionVehiculo.mockRejectedValue(
      apiError(409, {
        error: 'placa_con_suscripcion_activa',
        placa: 'ABC123',
        uuid_subscripcion_cliente: 'otra-sub',
      }),
    );
    await renderCreate(onSubmit, onDone);

    await userEvent.selectOptions(
      screen.getByTestId('suscripcion-field-plan'),
      '33333333-3333-3333-3333-333333333333',
    );
    await addVehiculo(0, 'veh-1');
    await userEvent.click(screen.getByTestId('suscripcion-form-submit'));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      const text = screen.getByTestId('suscripcion-vehiculo-error-0').textContent ?? '';
      expect(text).toMatch(/ABC123/);
      expect(text).toMatch(/otra suscripción activa/);
    });
    // The subscripcion itself was saved -- onDone must NOT fire (dialog
    // stays open so the admin sees which vehiculo failed), but onSubmit
    // (the save) already ran exactly once and is not retried.
    expect(onDone).not.toHaveBeenCalled();
  });

  it('does NOT create the subscripcion when the plate is already active in the branch (dry-run rejects first)', async () => {
    const onSubmit = vi.fn();
    const onDone = vi.fn();
    mockValidarAlta.mockRejectedValue(
      apiError(409, {
        error: 'placa_con_suscripcion_activa',
        placa: 'ABC123',
        uuid_vehiculo: 'veh-1',
        uuid_subscripcion_cliente: 'otra-sub',
      }),
    );
    await renderCreate(onSubmit, onDone);
    await userEvent.selectOptions(
      screen.getByTestId('suscripcion-field-plan'),
      '33333333-3333-3333-3333-333333333333',
    );
    await addVehiculo(0, 'veh-1');
    await userEvent.click(screen.getByTestId('suscripcion-form-submit'));

    await waitFor(() => {
      expect(screen.getByTestId('suscripcion-vehiculo-error-0').textContent).toMatch(/ABC123/);
    });
    expect(screen.getByTestId('suscripcion-form-submit-error').textContent).toMatch(
      /No se creó la suscripción/,
    );
    expect(onSubmit).not.toHaveBeenCalled();
    expect(mockCreateSubscripcionVehiculo).not.toHaveBeenCalled();
    expect(onDone).not.toHaveBeenCalled();
    expect(mockValidarAlta).toHaveBeenCalledWith({
      uuid_tipo_subscripcion: '33333333-3333-3333-3333-333333333333',
      uuid_vehiculos: ['veh-1'],
    });
  });

  it('does NOT create the subscripcion on a plan/quantity error not attributable to one vehicle', async () => {
    const onSubmit = vi.fn();
    mockValidarAlta.mockRejectedValue(
      apiError(422, { error: 'cantidad_vehiculos_excede_plan', cantidad_maxima_vehiculos: 2 }),
    );
    await renderCreate(onSubmit);
    await userEvent.selectOptions(
      screen.getByTestId('suscripcion-field-plan'),
      '33333333-3333-3333-3333-333333333333',
    );
    await addVehiculo(0, 'veh-1');
    await userEvent.click(screen.getByTestId('suscripcion-form-submit'));

    await waitFor(() => {
      expect(screen.getByTestId('suscripcion-form-submit-error').textContent).toMatch(
        /No se creó la suscripción.*cantidad máxima/,
      );
    });
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('does NOT create the subscripcion when the same vehicle is added twice', async () => {
    const onSubmit = vi.fn();
    await renderCreate(onSubmit);
    await userEvent.selectOptions(
      screen.getByTestId('suscripcion-field-plan'),
      '33333333-3333-3333-3333-333333333333',
    );
    await addVehiculo(0, 'veh-1');
    await addVehiculo(1, 'veh-1');
    await userEvent.click(screen.getByTestId('suscripcion-form-submit'));

    await waitFor(() => {
      expect(screen.getByTestId('suscripcion-form-submit-error').textContent).toMatch(
        /vehículos repetidos/,
      );
    });
    expect(onSubmit).not.toHaveBeenCalled();
    expect(mockValidarAlta).not.toHaveBeenCalled();
  });

  it('skips the dry-run when no vehicle was added', async () => {
    const onSubmit = vi.fn().mockResolvedValue({ ...VIGENTE, uuid: 'sub-new' });
    await renderCreate(onSubmit);
    await userEvent.selectOptions(
      screen.getByTestId('suscripcion-field-plan'),
      '33333333-3333-3333-3333-333333333333',
    );
    await userEvent.click(screen.getByTestId('suscripcion-form-submit'));
    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledTimes(1);
    });
    expect(mockValidarAlta).not.toHaveBeenCalled();
  });

  it('keeps the legacy 422 placa_con_suscripcion_vigente code as an alias', async () => {
    const onSubmit = vi.fn().mockResolvedValue({ ...VIGENTE, uuid: 'sub-new' });
    mockCreateSubscripcionVehiculo.mockRejectedValue(
      new Error(
        'clientesApi: POST /api/v1/clientes/subscripcion-vehiculos -> 422: {"error": "placa_con_suscripcion_vigente"}',
      ),
    );
    await renderCreate(onSubmit);
    await userEvent.selectOptions(
      screen.getByTestId('suscripcion-field-plan'),
      '33333333-3333-3333-3333-333333333333',
    );
    await addVehiculo(0, 'veh-1');
    await userEvent.click(screen.getByTestId('suscripcion-form-submit'));

    await waitFor(() => {
      expect(screen.getByTestId('suscripcion-vehiculo-error-0').textContent).toMatch(
        /otra suscripción activa/,
      );
    });
  });

  it.each([
    [403, { error: 'permission_denied' }, /supervisor/],
    [400, { error: 'missing_sucursal_context' }, /sucursal/i],
    [403, { error: 'unauthorized_sucursal_context' }, /acceso a la sucursal/],
    [409, { error: 'vehiculo_ya_inscrito' }, /ya está inscrito/],
    [422, { error: 'tipo_vehiculo_plan_incompatible', tipo_plan: 'moto' }, /no es compatible con el plan/],
    [422, { error: 'cantidad_maxima_excedida' }, /cantidad máxima/],
    [422, { error: 'tipo_vehiculo_incompatible' }, /mismo tipo/],
  ])('maps %s %j to a clear Spanish message', async (status, detail, pattern) => {
    const onSubmit = vi.fn().mockResolvedValue({ ...VIGENTE, uuid: 'sub-new' });
    mockCreateSubscripcionVehiculo.mockRejectedValue(apiError(status, detail));
    await renderCreate(onSubmit);
    await userEvent.selectOptions(
      screen.getByTestId('suscripcion-field-plan'),
      '33333333-3333-3333-3333-333333333333',
    );
    await addVehiculo(0, 'veh-1');
    await userEvent.click(screen.getByTestId('suscripcion-form-submit'));

    await waitFor(() => {
      expect(screen.getByTestId('suscripcion-vehiculo-error-0').textContent).toMatch(pattern);
    });
  });

  it('PT-2: only offers plans compatible with the vehicle type already added', async () => {
    await renderCreate();
    // No vehicle yet: every plan is offered.
    expect(planOptionLabels()).toEqual(
      expect.arrayContaining(['Mensual cualquiera', 'Mensual carro', 'Mensual moto']),
    );

    await addVehiculo(0, 'veh-1'); // carro
    await waitFor(() => {
      const labels = planOptionLabels();
      expect(labels).toContain('Mensual carro');
      expect(labels).toContain('Mensual cualquiera');
      expect(labels).not.toContain('Mensual moto');
    });
  });

  it('PT-2: blocks the save (before creating the subscripcion) when the chosen plan does not match the vehicle type', async () => {
    const onSubmit = vi.fn();
    await renderCreate(onSubmit);
    // Pick a moto plan first, then add a carro vehicle -> incompatible.
    await userEvent.selectOptions(screen.getByTestId('suscripcion-field-plan'), PLAN_MOTO.uuid);
    await addVehiculo(0, 'veh-1');

    await waitFor(() => {
      expect(screen.getByTestId('suscripcion-plan-incompatible')).toBeInTheDocument();
    });
    await userEvent.click(screen.getByTestId('suscripcion-form-submit'));
    await waitFor(() => {
      expect(screen.getByTestId('suscripcion-form-submit-error').textContent).toMatch(
        /no es compatible con el tipo de los vehículos/,
      );
    });
    expect(onSubmit).not.toHaveBeenCalled();
    expect(mockCreateSubscripcionVehiculo).not.toHaveBeenCalled();
  });
});

describe('<SuscripcionForm /> -- editar', () => {
  it('pre-fills dias_alerta_pre_vencimiento from the existing subscripcion', async () => {
    render(
      <SuscripcionForm
        subscripcion={VIGENTE}
        onSubmit={vi.fn()}
        onDone={vi.fn()}
        onCancel={vi.fn()}
      />,
      { wrapper },
    );

    await waitFor(() => {
      expect(
        (screen.getByTestId('suscripcion-field-dias-alerta') as HTMLInputElement).value,
      ).toBe('15');
    });
    // Edit mode never shows the "sin sucursal" guard (editing an
    // existing row doesn't need a freshly-selected sucursal).
    expect(screen.queryByTestId('suscripcion-form-sin-sucursal')).not.toBeInTheDocument();
  });
});
