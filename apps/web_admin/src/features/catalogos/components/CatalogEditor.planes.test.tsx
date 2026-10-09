/**
 * Plan administration with "Tipo de vehículo" (PT-2): the plans catalog
 * (`tipo-subscripciones`) shows the vehicle type per plan and lets the
 * admin assign it on create/edit. The dialog's selects for vehicle type
 * and client type do NOT have a "Cualquiera" option — once a plan is
 * assigned, the backend's `exclude_none` makes it impossible to go back
 * to NULL, so the UI matches the contract: pick one, always.
 *
 * The TABLE cell (`TipoVehiculoCell`) still renders "Cualquiera" for
 * null `uuid_tipo_vehiculo` — that's a display choice, not a form state,
 * and is the only place the user reads "Cualquiera" anymore.
 */
import { createElement, type ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SWRConfig } from 'swr';
import type * as CatalogApiModule from '../api/catalogApi';

const TIPO_CARRO = '44444444-4444-4444-8444-444444444444';
const TIPO_MOTO = '55555555-5555-4555-8555-555555555555';
const PLAN_ANY = '11111111-1111-4111-8111-111111111111';
const PLAN_MOTO = '22222222-2222-4222-8222-222222222222';
const PLAN_VIEJO = '88888888-8888-4888-8888-888888888888';
const TIPO_VIEJO = '99999999-9999-4999-8999-999999999999';
const PERSONA_NATURAL = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const PERSONA_JURIDICA = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';

const row = (over: Record<string, unknown>) => ({
  vigente_desde: '2026-01-01T00:00:00',
  vigente_hasta: null,
  estado: 'activo',
  valor: 30000,
  duracion_dias: 30,
  cantidad_maxima_vehiculos: 1,
  mismo_tipo_vehiculo: false,
  tipo_cliente_permitido: null,
  ...over,
});

const mockCreate = vi.fn();
const mockUpdate = vi.fn();

vi.mock('../api/catalogApi', async () => {
  const actual = await vi.importActual<typeof CatalogApiModule>('../api/catalogApi');
  return {
    ...actual,
    listCatalog: vi.fn(async (resource: string) => {
      if (resource === 'tipos-vehiculo') {
        return [
          row({ uuid: TIPO_CARRO, tipo: 'Carro' }),
          row({ uuid: TIPO_MOTO, tipo: 'Moto' }),
          row({
            uuid: TIPO_VIEJO,
            tipo: 'Bicicleta (versión anterior)',
            vigente_hasta: '2026-02-01T00:00:00',
            estado: 'inactivo',
          }),
        ];
      }
      if (resource === 'tipo-persona') {
        return [
          row({ uuid: PERSONA_NATURAL, tipo: 'Natural' }),
          row({ uuid: PERSONA_JURIDICA, tipo: 'Juridica' }),
        ];
      }
      return [
        row({ uuid: PLAN_ANY, tipo: 'Mensual cualquiera', uuid_tipo_vehiculo: null }),
        row({ uuid: PLAN_MOTO, tipo: 'Mensual moto', uuid_tipo_vehiculo: TIPO_MOTO }),
        row({ uuid: PLAN_VIEJO, tipo: 'Mensual bici', uuid_tipo_vehiculo: TIPO_VIEJO }),
      ];
    }),
    createCatalogVersion: (...a: unknown[]) => mockCreate(...a),
    updateCatalogVersion: (...a: unknown[]) => mockUpdate(...a),
  };
});

import { CatalogEditor } from './CatalogEditor';
import { tipoSubscripcionesConfig } from '../configs/tipoSubscripciones.config';

function wrapper({ children }: { children: ReactNode }): JSX.Element {
  return createElement(SWRConfig, { value: { provider: (): never => new Map() as never } }, children);
}

beforeEach(() => {
  mockCreate.mockReset().mockResolvedValue({});
  mockUpdate.mockReset().mockResolvedValue({});
});

/**
 * Open a Radix Select and pick the option whose visible text matches
 * `optionLabel`. Wraps the two `user.click` calls so the tests stay
 * focused on the data flow rather than the trigger/option event
 * mechanics.
 */
async function pickOption(
  trigger: HTMLElement,
  optionLabel: string,
): Promise<HTMLElement> {
  const user = userEvent.setup();
  await user.click(trigger);
  const option = await screen.findByRole('option', { name: optionLabel });
  await user.click(option);
  return option;
}

describe('Planes: tipo de vehículo', () => {
  it('lists the vehicle type of each plan ("Cualquiera" when none in the table cell)', async () => {
    render(<CatalogEditor config={tipoSubscripcionesConfig} />, { wrapper });

    const rowAny = await screen.findByTestId(`catalog-row-${PLAN_ANY}`);
    const rowMoto = await screen.findByTestId(`catalog-row-${PLAN_MOTO}`);
    expect(within(rowAny).getByText('Cualquiera')).toBeInTheDocument();
    await waitFor(() => {
      expect(within(rowMoto).getByText('Moto')).toBeInTheDocument();
    });
  });

  it('creates a plan with the chosen vehicle type', async () => {
    const user = userEvent.setup();
    render(<CatalogEditor config={tipoSubscripcionesConfig} />, { wrapper });
    await user.click(await screen.findByTestId('catalog-new-tipo-subscripciones'));

    await user.click(await screen.findByTestId('field-uuid_tipo_vehiculo'));
    const options = await screen.findAllByRole('option');
    expect(options.map((o) => o.textContent)).toEqual(['Carro', 'Moto']);

    await user.click(screen.getByRole('option', { name: 'Carro' }));
    await user.type(screen.getByTestId('field-tipo'), 'Mensual carro');
    await user.click(screen.getByTestId('submit-nueva-version'));

    await waitFor(() => {
      expect(mockCreate).toHaveBeenCalledTimes(1);
    });
    expect(mockCreate.mock.calls[0]?.[0]).toBe('tipo-subscripciones');
    expect(mockCreate.mock.calls[0]?.[1]).toMatchObject({
      tipo: 'Mensual carro',
      uuid_tipo_vehiculo: TIPO_CARRO,
    });
  });

  it('blocks submit when the vehicle type is required and not picked', async () => {
    const user = userEvent.setup();
    render(<CatalogEditor config={tipoSubscripcionesConfig} />, { wrapper });
    await user.click(await screen.findByTestId('catalog-new-tipo-subscripciones'));
    await user.type(await screen.findByTestId('field-tipo'), 'Mensual libre');
    await user.click(screen.getByTestId('submit-nueva-version'));

    // Radix Select requires a value to be picked (no "Cualquiera"). The
    // empty form value fails Zod's `z.string().min(1)`, so the submit
    // is blocked before reaching the network.
    expect(mockCreate).not.toHaveBeenCalled();
  });

  it('edits a plan changing its vehicle type (PUT carries uuid_tipo_vehiculo)', async () => {
    const user = userEvent.setup();
    render(<CatalogEditor config={tipoSubscripcionesConfig} />, { wrapper });
    await user.click(await screen.findByTestId(`catalog-row-${PLAN_ANY}`));
    const trigger = await screen.findByTestId('field-uuid_tipo_vehiculo');
    // The trigger shows the label of the row's current vehicle type
    // (null → placeholder; for PLAN_ANY the cell is "Cualquiera" but
    // the dialog's select trigger has no value, so it shows the
    // placeholder).
    await pickOption(trigger, 'Moto');
    await user.click(screen.getByTestId('submit-nueva-version'));

    await waitFor(() => expect(mockUpdate).toHaveBeenCalledTimes(1));
    expect(mockUpdate.mock.calls[0]?.[1]).toBe(PLAN_ANY);
    expect(mockUpdate.mock.calls[0]?.[2]).toMatchObject({ uuid_tipo_vehiculo: TIPO_MOTO });
  });

  it('keeps a plan whose type points at an older (no longer vigente) version selectable, instead of forcing the user to re-pick', async () => {
    const user = userEvent.setup();
    render(<CatalogEditor config={tipoSubscripcionesConfig} />, { wrapper });
    await user.click(await screen.findByTestId(`catalog-row-${PLAN_VIEJO}`));
    const trigger = await screen.findByTestId('field-uuid_tipo_vehiculo');
    // The trigger should show the stale option's label.
    await waitFor(() => {
      expect(trigger).toHaveTextContent(/Bicicleta/);
    });
    await user.click(screen.getByTestId('submit-nueva-version'));

    await waitFor(() => expect(mockUpdate).toHaveBeenCalledTimes(1));
    expect(mockUpdate.mock.calls[0]?.[2]).toMatchObject({ uuid_tipo_vehiculo: TIPO_VIEJO });
    expect(screen.queryByTestId('nueva-version-submit-error')).not.toBeInTheDocument();
  });

  it('tipo_cliente_permitido is a select populated by tipos-persona and saves the `tipo` string (not the uuid); no "Cualquiera"', async () => {
    const user = userEvent.setup();
    render(<CatalogEditor config={tipoSubscripcionesConfig} />, { wrapper });
    await user.click(await screen.findByTestId('catalog-new-tipo-subscripciones'));

    const trigger = await screen.findByTestId('field-tipo_cliente_permitido');
    await user.click(trigger);
    const options = await screen.findAllByRole('option');
    // Natural + Juridica only — no "Cualquiera" anymore.
    expect(options.map((o) => o.textContent)).toEqual(['Natural', 'Juridica']);

    await user.click(screen.getByRole('option', { name: 'Juridica' }));
    // uuid_tipo_vehiculo is now required too — pick a vehicle type so
    // the submit is not blocked by Zod before reaching the network.
    await user.click(screen.getByTestId('field-uuid_tipo_vehiculo'));
    await user.click(screen.getByRole('option', { name: 'Carro' }));
    await user.type(screen.getByTestId('field-tipo'), 'Plan premium');
    await user.click(screen.getByTestId('submit-nueva-version'));

    await waitFor(() => expect(mockCreate).toHaveBeenCalledTimes(1));
    expect(mockCreate.mock.calls[0]?.[1]).toMatchObject({
      tipo: 'Plan premium',
      tipo_cliente_permitido: 'Juridica',
      uuid_tipo_vehiculo: TIPO_CARRO,
    });
  });
});
