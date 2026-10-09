/**
 * UX tests for /catalogos: 409 error mapping rendered INSIDE the dialog,
 * JSON validation for `caracteristicas`, and constrained selects for
 * `tipo_calculo` / `base_calculo` in Impuestos / Otros cobros / Costos
 * de servicios.
 */
import { createElement, type ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SWRConfig } from 'swr';

import { ParkosHttpError } from '@/lib/fetch';
import type * as CatalogApiModule from '../api/catalogApi';
import { CatalogEditor } from './CatalogEditor';
import { impuestosConfig } from '../configs/impuestos.config';
import { otrosCobrosConfig } from '../configs/otrosCobros.config';
import { costosServiciosConfig } from '../configs/costosServicios.config';
import { tipoSucursalConfig } from '../configs/tipoSucursal.config';

const IMP_IVA = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const COBRO_LAVADO = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc';
const SERV_LAVADO = 'dddddddd-dddd-4ddd-8ddd-dddddddddddd';
const SUCURSAL_CENTRO = 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee';

const row = (over: Record<string, unknown>) => ({
  vigente_desde: '2026-01-01T00:00:00',
  vigente_hasta: null,
  estado: 'activo',
  ...over,
});

const mockCreate = vi.fn();
const mockUpdate = vi.fn();

vi.mock('../api/catalogApi', async () => {
  const actual = await vi.importActual<typeof CatalogApiModule>('../api/catalogApi');
  return {
    ...actual,
    listCatalog: vi.fn(async (resource: string) => {
      if (resource === 'impuestos') {
        return [row({ uuid: IMP_IVA, codigo: 'IVA', nombre: 'IVA 19%', porcentaje: 19 })];
      }
      if (resource === 'otros-cobros') {
        return [row({ uuid: COBRO_LAVADO, nombre: 'Lavado' })];
      }
      if (resource === 'costos-servicios') {
        return [row({ uuid: SERV_LAVADO, concepto: 'Lavado' })];
      }
      if (resource === 'tipo-sucursal') {
        return [row({ uuid: SUCURSAL_CENTRO, codigo: 'CENTRO', nombre: 'Centro' })];
      }
      return [];
    }),
    createCatalogVersion: (...a: unknown[]) => mockCreate(...a),
    updateCatalogVersion: (...a: unknown[]) => mockUpdate(...a),
  };
});

function wrapper({ children }: { children: ReactNode }): JSX.Element {
  return createElement(
    SWRConfig,
    { value: { provider: (): never => new Map() as never } },
    children,
  );
}

beforeEach(() => {
  mockCreate.mockReset();
  mockUpdate.mockReset();
});

describe('CatalogEditor: tipos_vehiculo_max_reached (item 2)', () => {
  it('renders the cap message inside the dialog when the backend returns 409 with the typed error code', async () => {
    const body = JSON.stringify({
      detail: { error: 'tipos_vehiculo_max_reached', limit: 5, current: 5 },
    });
    mockCreate.mockRejectedValueOnce(new ParkosHttpError(409, body, '/api/v1/catalogos/tipos-vehiculo'));
    // Render impuestos config to use a known dialog with submit.
    const user = userEvent.setup();
    render(<CatalogEditor config={impuestosConfig} />, { wrapper });
    await user.click(await screen.findByTestId('catalog-new-impuestos'));
    await user.type(await screen.findByTestId('field-codigo'), 'IMPCONSA');
    await user.click(screen.getByTestId('submit-nueva-version'));

    const err = await screen.findByTestId('nueva-version-submit-error');
    expect(err).toHaveTextContent(/5 tipos de vehículo vigentes/);
    expect(err).toHaveTextContent(/máximo permitido es 5/);
    expect(mockCreate).toHaveBeenCalledTimes(1);
  });
});

describe('CatalogEditor: caracteristicas JSON validation (item 4)', () => {
  it('blocks submit with inline error when caracteristicas is not valid JSON', async () => {
    const user = userEvent.setup();
    render(<CatalogEditor config={tipoSucursalConfig} />, { wrapper });
    await user.click(await screen.findByTestId('catalog-new-tipo-sucursal'));
    await user.type(await screen.findByTestId('field-codigo'), 'NORTE');
    // `caracteristicas` defaults to "{}" which is valid; replace with bad input
    const ta = (await screen.findByTestId('field-caracteristicas')) as HTMLTextAreaElement;
    fireEvent.change(ta, { target: { value: '{ techado: true' } });
    await user.click(screen.getByTestId('submit-nueva-version'));

    const err = await screen.findByTestId('nueva-version-submit-error');
    expect(err).toHaveTextContent(/JSON inválido/);
    expect(mockCreate).not.toHaveBeenCalled();
  });

  it('blocks submit when caracteristicas is a JSON array (not an object)', async () => {
    const user = userEvent.setup();
    render(<CatalogEditor config={tipoSucursalConfig} />, { wrapper });
    await user.click(await screen.findByTestId('catalog-new-tipo-sucursal'));
    await user.type(await screen.findByTestId('field-codigo'), 'NORTE');
    const ta = (await screen.findByTestId('field-caracteristicas')) as HTMLTextAreaElement;
    fireEvent.change(ta, { target: { value: '[1,2,3]' } });
    await user.click(screen.getByTestId('submit-nueva-version'));

    const err = await screen.findByTestId('nueva-version-submit-error');
    expect(err).toHaveTextContent(/objeto JSON/);
    expect(mockCreate).not.toHaveBeenCalled();
  });

  it('parses valid JSON and sends the dict to the backend', async () => {
    const user = userEvent.setup();
    render(<CatalogEditor config={tipoSucursalConfig} />, { wrapper });
    await user.click(await screen.findByTestId('catalog-new-tipo-sucursal'));
    await user.type(await screen.findByTestId('field-codigo'), 'NORTE');
    const ta = (await screen.findByTestId('field-caracteristicas')) as HTMLTextAreaElement;
    fireEvent.change(ta, { target: { value: '{"techado": true, "capacidad": 50}' } });
    mockCreate.mockResolvedValueOnce({});
    await user.click(screen.getByTestId('submit-nueva-version'));

    await waitFor(() => expect(mockCreate).toHaveBeenCalledTimes(1));
    expect(mockCreate.mock.calls[0]?.[0]).toBe('tipo-sucursal');
    expect(mockCreate.mock.calls[0]?.[1]).toMatchObject({
      codigo: 'NORTE',
      caracteristicas: { techado: true, capacidad: 50 },
    });
  });

  it('serializes a dict on edit back to a JSON string in the textarea', async () => {
    // Patch the mock to return one row with a dict so we can exercise the
    // edit path.
    const { listCatalog } = await import('../api/catalogApi');
    (listCatalog as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce([
      row({
        uuid: SUCURSAL_CENTRO,
        codigo: 'CENTRO',
        nombre: 'Centro',
        caracteristicas: { techado: true, capacidad: 50 },
      }),
    ]);
    const user = userEvent.setup();
    render(<CatalogEditor config={tipoSucursalConfig} />, { wrapper });
    await user.click(await screen.findByTestId(`catalog-row-${SUCURSAL_CENTRO}`));
    const ta = (await screen.findByTestId('field-caracteristicas')) as HTMLTextAreaElement;
    await waitFor(() => {
      expect(ta.value).toContain('"techado"');
      expect(ta.value).toContain('"capacidad": 50');
    });
  });
});

describe('CatalogEditor: tipo_calculo / base_calculo as constrained selects (item 5)', () => {
  it('Impuestos: tipo_calculo and base_calculo render as selects with the canonical values', async () => {
    const user = userEvent.setup();
    render(<CatalogEditor config={impuestosConfig} />, { wrapper });
    await user.click(await screen.findByTestId('catalog-new-impuestos'));
    await user.type(await screen.findByTestId('field-codigo'), 'IVA2');

    const tipo = (await screen.findByTestId('field-tipo_calculo')) as HTMLSelectElement;
    expect(tipo.tagName).toBe('SELECT');
    await waitFor(() => expect(tipo.options.length).toBe(3));
    expect(tipo.options[0]?.textContent).toBe('Sin definir');
    expect(tipo.options[1]?.value).toBe('porcentaje');
    expect(tipo.options[2]?.value).toBe('fijo');

    const base = (await screen.findByTestId('field-base_calculo')) as HTMLSelectElement;
    expect(base.tagName).toBe('SELECT');
    await waitFor(() => expect(base.options.length).toBe(3));
    expect(base.options[0]?.textContent).toBe('Sin definir');
    expect(base.options[1]?.value).toBe('subtotal');
    expect(base.options[2]?.value).toBe('total');

    await user.selectOptions(tipo, 'porcentaje');
    await user.selectOptions(base, 'subtotal');
    mockCreate.mockResolvedValueOnce({});
    await user.click(screen.getByTestId('submit-nueva-version'));

    await waitFor(() => expect(mockCreate).toHaveBeenCalledTimes(1));
    expect(mockCreate.mock.calls[0]?.[1]).toMatchObject({
      codigo: 'IVA2',
      tipo_calculo: 'porcentaje',
      base_calculo: 'subtotal',
    });
  });

  it('Otros cobros: tipo_calculo and base_calculo render as selects', async () => {
    const user = userEvent.setup();
    render(<CatalogEditor config={otrosCobrosConfig} />, { wrapper });
    await user.click(await screen.findByTestId('catalog-new-otros-cobros'));
    await user.type(await screen.findByTestId('field-nombre'), 'Lavado premium');

    const tipo = (await screen.findByTestId('field-tipo_calculo')) as HTMLSelectElement;
    const base = (await screen.findByTestId('field-base_calculo')) as HTMLSelectElement;
    expect(tipo.tagName).toBe('SELECT');
    expect(base.tagName).toBe('SELECT');
    expect(tipo.options.length).toBe(3);
    expect(base.options.length).toBe(3);
  });

  it('Costos de servicios: tipo_calculo is a select (no base_calculo field)', async () => {
    const user = userEvent.setup();
    render(<CatalogEditor config={costosServiciosConfig} />, { wrapper });
    await user.click(await screen.findByTestId('catalog-new-costos-servicios'));
    await user.type(await screen.findByTestId('field-concepto'), 'Reimpresión');

    const tipo = (await screen.findByTestId('field-tipo_calculo')) as HTMLSelectElement;
    expect(tipo.tagName).toBe('SELECT');
    expect(tipo.options.length).toBe(3);
    expect(screen.queryByTestId('field-base_calculo')).not.toBeInTheDocument();
  });
});
