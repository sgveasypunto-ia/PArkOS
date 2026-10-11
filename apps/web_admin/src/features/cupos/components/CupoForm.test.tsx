/**
 * `CupoForm.test.tsx` — boundary-equality UX defense for the EDIT modal.
 *
 * The operator-reported bug: re-editing a cupo with a ``vigente_desde``
 * at or before the row's current ``vigente_desde`` slips past the
 * front-end and gets a 409 ``cantidad_overlap`` from the backend's
 * ``<=`` pre-check at ``empresa.py:1143``. The fix is a guard inside
 * ``<CupoForm />`` that:
 *
 * 1. Computes ``isBoundaryEdit`` by comparing the form's current
 *    ``vigente_desde`` with ``initialCupo.vigente_desde``.
 * 2. Renders an inline warning (``cupo-field-vigente-desde-boundary-warning``).
 * 3. Disables the submit button.
 *
 * This test pins all three behaviors. CREATE has no current row, so
 * the guard must be a no-op there (regression).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { CupoFormHarness } from './CupoForm';
import type { Cupo } from '../api/cupoSchema';

/**
 * Set the value of the ``<input type="datetime-local">`` field. The
 * form's onChange handler explicitly REJECTS empty strings (the field
 * is required by the Zod schema), and ``userEvent.type`` /
 * ``userEvent.clear`` interact poorly with datetime-local inputs under
 * jsdom — the typed value often ends up appended to the existing
 * placeholder. ``fireEvent.change`` is the lowest-friction way to
 * dispatch a clean value change.
 */
function setVigenteDesde(input: HTMLInputElement, value: string): void {
  fireEvent.change(input, { target: { value } });
}

const SUCURSAL_UUID = '11111111-1111-1111-1111-111111111111';
const TIPO_CARRO = '00000000-0000-0000-0000-000000000001';

function makeCupo(overrides: Partial<Cupo> = {}): Cupo {
  return {
    uuid: 'aaaaaaaa-1111-1111-1111-111111111111',
    uuid_sucursal: SUCURSAL_UUID,
    uuid_tipo_vehiculo: TIPO_CARRO,
    cantidad: 10,
    vigente_desde: '2026-10-10T19:06:00+00:00',
    vigente_hasta: null,
    estado: 'activo',
    created_at: '2026-10-10T19:06:00+00:00',
    created_by: null,
    sync_status: 'sincronizado',
    ...overrides,
  };
}

const TIPOS = [
  {
    uuid: TIPO_CARRO,
    tipo: 'carro',
    vigente_desde: '2026-01-01T00:00:00',
    vigente_hasta: null,
    estado: 'activo',
    created_at: '2026-01-01T00:00:00',
    created_by: null,
    sync_status: 'sincronizado',
  },
];

beforeEach(() => {
  // The harness does not need a real network. The submit callback is
  // spied per-test; we only assert the form's interactive state.
});

describe('CupoForm — boundary-equality UX defense', () => {
  it('CPF1 (EDIT default): submit stays enabled because the default "now+1min" is strictly after the existing vigente_desde', async () => {
    render(
      <CupoFormHarness
        onSubmit={vi.fn()}
        isSubmitting={false}
        isUpdate
        initialCupo={makeCupo({ vigente_desde: '2020-01-01T00:00:00' })}
        onCancel={vi.fn()}
        sucursalNombre="Sucursal Centro"
        tiposVehiculo={TIPOS}
        tiposEnUsoEnSucursal={new Set()}
        onTipoCreated={vi.fn()}
      />,
    );
    // The boundary warning is NOT shown (the form's default
    // "now+1min" is after any past date in the fixture).
    expect(
      screen.queryByTestId('cupo-field-vigente-desde-boundary-warning'),
    ).not.toBeInTheDocument();
    // The submit button is enabled.
    const submit = screen.getByTestId('cupo-submit') as HTMLButtonElement;
    expect(submit.disabled).toBe(false);
  });

  it('CPF2 (EDIT, boundary equality): when the operator types the SAME vigente_desde as the row, the warning appears and the submit button is disabled', async () => {
    const onSubmit = vi.fn();
    const existingVigenteDesde = '2026-10-10T19:06:00+00:00';
    render(
      <CupoFormHarness
        onSubmit={onSubmit}
        isSubmitting={false}
        isUpdate
        initialCupo={makeCupo({ vigente_desde: existingVigenteDesde })}
        onCancel={vi.fn()}
        sucursalNombre="Sucursal Centro"
        tiposVehiculo={TIPOS}
        tiposEnUsoEnSucursal={new Set()}
        onTipoCreated={vi.fn()}
      />,
    );
    // The harness pre-fills the input with "now+1min"; overwrite
    // it with the boundary-equal value to simulate the operator
    // typing the same instant the row already has.
    const dateInput = screen.getByTestId(
      'cupo-field-vigente-desde',
    ) as HTMLInputElement;
    const local = existingVigenteDesde.slice(0, 16); // 'YYYY-MM-DDTHH:mm'
    setVigenteDesde(dateInput, local);
    await waitFor(() => {
      expect(
        screen.getByTestId('cupo-field-vigente-desde-boundary-warning'),
      ).toBeInTheDocument();
    });
    // The submit button is disabled while the boundary is active.
    const submit = screen.getByTestId('cupo-submit') as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
    // Clicking submit does NOT call onSubmit.
    await userEvent.setup().click(submit);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('CPF3 (EDIT, backward date): the same warning fires for ANY vigente_desde strictly BEFORE the row', async () => {
    render(
      <CupoFormHarness
        onSubmit={vi.fn()}
        isSubmitting={false}
        isUpdate
        initialCupo={makeCupo({ vigente_desde: '2026-10-10T19:06:00+00:00' })}
        onCancel={vi.fn()}
        sucursalNombre="Sucursal Centro"
        tiposVehiculo={TIPOS}
        tiposEnUsoEnSucursal={new Set()}
        onTipoCreated={vi.fn()}
      />,
    );
    const dateInput = screen.getByTestId(
      'cupo-field-vigente-desde',
    ) as HTMLInputElement;
    setVigenteDesde(dateInput, '2020-01-01T00:00');
    await waitFor(() => {
      expect(
        screen.getByTestId('cupo-field-vigente-desde-boundary-warning'),
      ).toBeInTheDocument();
    });
    const submit = screen.getByTestId('cupo-submit') as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
  });

  it('CPF4 (EDIT, forward date): the warning is NOT shown and submit IS enabled when the operator picks a strictly future vigente_desde', async () => {
    const onSubmit = vi.fn();
    render(
      <CupoFormHarness
        onSubmit={onSubmit}
        isSubmitting={false}
        isUpdate
        initialCupo={makeCupo({ vigente_desde: '2020-01-01T00:00:00' })}
        onCancel={vi.fn()}
        sucursalNombre="Sucursal Centro"
        tiposVehiculo={TIPOS}
        tiposEnUsoEnSucursal={new Set()}
        onTipoCreated={vi.fn()}
      />,
    );
    // The default is "now+1min" — strictly after 2020-01-01 — so
    // the warning is absent and the submit button is enabled from
    // the start. The form must accept the submit and call onSubmit.
    expect(
      screen.queryByTestId('cupo-field-vigente-desde-boundary-warning'),
    ).not.toBeInTheDocument();
    const submit = screen.getByTestId('cupo-submit') as HTMLButtonElement;
    expect(submit.disabled).toBe(false);
    await userEvent.setup().click(submit);
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
  });

  it('CPF5 (CREATE): the guard is a no-op — no warning, submit always enabled regardless of vigente_desde', async () => {
    const onSubmit = vi.fn();
    render(
      <CupoFormHarness
        onSubmit={onSubmit}
        isSubmitting={false}
        isUpdate={false}
        initialCupo={null}
        onCancel={vi.fn()}
        sucursalNombre="Sucursal Centro"
        tiposVehiculo={TIPOS}
        tiposEnUsoEnSucursal={new Set()}
        onTipoCreated={vi.fn()}
      />,
    );
    // Even when the operator types a past date on CREATE, the
    // guard must not fire — there is no current row to compare
    // against, the backend's overlap check is the only authority.
    const dateInput = screen.getByTestId(
      'cupo-field-vigente-desde',
    ) as HTMLInputElement;
    setVigenteDesde(dateInput, '2020-01-01T00:00');
    expect(
      screen.queryByTestId('cupo-field-vigente-desde-boundary-warning'),
    ).not.toBeInTheDocument();
    const submit = screen.getByTestId('cupo-submit') as HTMLButtonElement;
    expect(submit.disabled).toBe(false);
  });
});
