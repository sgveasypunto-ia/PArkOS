/**
 * `SuscripcionForm.test.tsx` — HU-F20.2 crear/editar suscripción.
 *
 * Covers: the "sin sucursal" guard (CREATE mode only), the prorrateo
 * panel (BR2), submitting a CREATE with one vehiculo that gets a 422
 * `placa_con_suscripcion_vigente` (mapped to a readable inline message
 * without blocking the already-saved subscripcion), and the EDIT-mode
 * defaults (`dias_alerta_pre_vencimiento` pre-filled from the existing
 * row).
 */
import { createElement } from 'react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { SUCURSAL_STORAGE_KEY, SucursalProvider } from '@/lib/sucursal-context';

const { PLAN, VIGENTE } = vi.hoisted(() => ({
  PLAN: {
    uuid: '33333333-3333-3333-3333-333333333333',
    vigente_desde: '2026-01-01T00:00:00',
    vigente_hasta: null,
    estado: 'activo',
    tipo: 'Mensual carro',
    valor: 30000,
    duracion_dias: 30,
    cantidad_maxima_vehiculos: 2,
    mismo_tipo_vehiculo: false,
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
}));

const mockCreateSubscripcionVehiculo = vi.fn();
const mockListVehiculos = vi.fn().mockResolvedValue({
  items: [{ uuid: 'veh-1', placa: 'ABC123', uuid_tipo_vehiculo: null, estado: 'activo' }],
  next_cursor: null,
});

vi.mock('../api/clientesApi', () => ({
  createSubscripcionVehiculo: (...args: unknown[]) => mockCreateSubscripcionVehiculo(...args),
  listVehiculos: (...args: unknown[]) => mockListVehiculos(...args),
}));

vi.mock('@/features/catalogos/api/catalogApi', () => ({
  listCatalog: vi.fn().mockResolvedValue([PLAN]),
}));

import { SuscripcionForm } from './SuscripcionForm';

function wrapper({ children }: { children: ReactNode }): JSX.Element {
  return createElement(SucursalProvider, null, children);
}

beforeEach(() => {
  window.localStorage.removeItem(SUCURSAL_STORAGE_KEY);
  mockCreateSubscripcionVehiculo.mockReset();
  mockListVehiculos.mockClear();
});

describe('<SuscripcionForm /> -- crear', () => {
  it('disables submit and shows a guard when no sucursal is selected', async () => {
    const onSubmit = vi.fn();
    render(
      <SuscripcionForm onSubmit={onSubmit} onDone={vi.fn()} onCancel={vi.fn()} />,
      { wrapper },
    );

    await waitFor(() => {
      expect(screen.getByTestId('suscripcion-form-sin-sucursal')).toBeInTheDocument();
    });
    expect(screen.getByTestId('suscripcion-form-submit')).toBeDisabled();
  });

  it('shows the FULL plan valor in the monto panel once a plan is set (no proration)', async () => {
    window.localStorage.setItem(SUCURSAL_STORAGE_KEY, 'suc-1');
    render(
      <SuscripcionForm onSubmit={vi.fn()} onDone={vi.fn()} onCancel={vi.fn()} />,
      { wrapper },
    );

    await waitFor(() => {
      expect(screen.getByTestId('suscripcion-field-plan')).toBeInTheDocument();
    });
    await userEvent.selectOptions(screen.getByTestId('suscripcion-field-plan'), '33333333-3333-3333-3333-333333333333');

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
    window.localStorage.setItem(SUCURSAL_STORAGE_KEY, 'suc-1');
    render(
      <SuscripcionForm onSubmit={vi.fn()} onDone={vi.fn()} onCancel={vi.fn()} />,
      { wrapper },
    );
    await waitFor(() => {
      expect(screen.getByTestId('suscripcion-field-plan')).toBeInTheDocument();
    });
    await userEvent.selectOptions(screen.getByTestId('suscripcion-field-plan'), '33333333-3333-3333-3333-333333333333');
    await userEvent.clear(screen.getByTestId('suscripcion-field-fecha-inicio'));
    await userEvent.type(screen.getByTestId('suscripcion-field-fecha-inicio'), '2026-09-01');
    // PLAN has duracion_dias = 30: Sep 1 + 29 = Sep 30.
    await waitFor(() => {
      expect(screen.getByTestId('suscripcion-field-fecha-vencimiento')).toHaveValue('2026-09-30');
    });
  });

  it('saves the subscripcion then maps a per-vehiculo 422 without losing the saved subscripcion', async () => {
    window.localStorage.setItem(SUCURSAL_STORAGE_KEY, 'suc-1');
    const onSubmit = vi.fn().mockResolvedValue({ ...VIGENTE, uuid: 'sub-new' });
    const onDone = vi.fn();
    mockCreateSubscripcionVehiculo.mockRejectedValue(
      new Error(
        'clientesApi: POST /api/v1/clientes/subscripcion-vehiculos -> 422: {"error": "placa_con_suscripcion_vigente"}',
      ),
    );

    render(
      <SuscripcionForm onSubmit={onSubmit} onDone={onDone} onCancel={vi.fn()} />,
      { wrapper },
    );

    await waitFor(() => {
      expect(screen.getByTestId('suscripcion-field-plan')).toBeInTheDocument();
    });
    await userEvent.selectOptions(screen.getByTestId('suscripcion-field-plan'), '33333333-3333-3333-3333-333333333333');
    await userEvent.click(screen.getByTestId('suscripcion-agregar-vehiculo'));

    await waitFor(() => {
      expect(screen.getByTestId('suscripcion-vehiculo-select-0')).toBeInTheDocument();
    });
    await userEvent.selectOptions(screen.getByTestId('suscripcion-vehiculo-select-0'), 'veh-1');

    await userEvent.click(screen.getByTestId('suscripcion-form-submit'));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(screen.getByTestId('suscripcion-vehiculo-error-0').textContent).toMatch(
        /suscripción vigente/,
      );
    });
    // The subscripcion itself was saved -- onDone must NOT fire (dialog
    // stays open so the admin sees which vehiculo failed), but onSubmit
    // (the save) already ran exactly once and is not retried.
    expect(onDone).not.toHaveBeenCalled();
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
