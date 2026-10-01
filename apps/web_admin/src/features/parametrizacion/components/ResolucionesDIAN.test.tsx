/**
 * `ResolucionesDIAN.test.tsx` — component-level tests for HU-F15.3's
 * "Resoluciones" tab (T6/T7: component wiring + minimum coverage list from
 * the HU).
 *
 * The entire API module (`resolucionFacturacionApi.ts`) is mocked, mirroring
 * `features/tarifas/pages/Tarifas.test.tsx`'s own
 * `vi.mock('../api/tarifasApi', () => ({...}))` convention — this file pins
 * the COMPONENT's behaviour (loading/empty/error/list/banner/create
 * wiring), not the HTTP layer's own 404-to-empty-list translation, which is
 * `resolucionFacturacionApi.ts::listResolucionesFacturacion`'s own
 * responsibility (documented in that file). The "404-como-vacío" test below
 * pins the observable CONSEQUENCE from this component's perspective: an
 * empty resolved list (which is exactly what a 404 degrades to once the API
 * layer translates it) must render the plain empty state, never an error.
 *
 * Covers:
 *   1. Lista vacía -> estado vacío claro (`resolucion-empty`), sin error.
 *   2. Lista con 1 resolución -> todos los campos de solo lectura visibles.
 *   3. Banner de agotamiento (BR2) cuando `consecutivo-actual` responde
 *      `agotandose: true` para una resolución vigente.
 *   4. 404-como-vacío: una lista resuelta vacía (lo que produce un 404 ya
 *      traducido por la capa API) nunca muestra el estado de error.
 *   5. (bonus) Flujo de creación: abre el formulario, envía los 4 campos,
 *      llama `createResolucionFacturacion` y refresca la lista.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SWRConfig } from 'swr';
import { createElement, type ReactNode } from 'react';

vi.mock('../api/resolucionFacturacionApi', () => ({
  listResolucionesFacturacion: vi.fn(),
  createResolucionFacturacion: vi.fn(),
  getConsecutivoActual: vi.fn(),
  ResolucionFacturacionVigenciaError: class ResolucionFacturacionVigenciaError extends Error {},
}));

import {
  listResolucionesFacturacion,
  createResolucionFacturacion,
  getConsecutivoActual,
} from '../api/resolucionFacturacionApi';
import { ResolucionesDIAN } from './ResolucionesDIAN';

const mockedList = listResolucionesFacturacion as ReturnType<typeof vi.fn>;
const mockedCreate = createResolucionFacturacion as ReturnType<typeof vi.fn>;
const mockedConsecutivo = getConsecutivoActual as ReturnType<typeof vi.fn>;

const SUCURSAL = '11111111-1111-1111-1111-111111111111';

const SAMPLE_RESOLUCION = {
  uuid: 'aaaaaaaa-1111-1111-1111-111111111111',
  uuid_sucursal: SUCURSAL,
  numero_resolucion: 'RES-0001',
  prefijo: 'FE',
  rango_desde: 1,
  rango_hasta: 5000,
  fecha_resolucion: '2026-01-01',
  fecha_inicio_vigencia: '2026-01-01',
  fecha_fin_vigencia: '2027-01-01',
  vigente_desde: '2026-01-01T00:00:00',
  vigente_hasta: null,
  estado: 'activo',
  created_at: '2026-01-01T00:00:00',
  created_by: null,
  sync_status: 'sincronizado',
};

// Fresh SWR cache per render — otherwise every test sharing `SUCURSAL`'s
// key would see the previous test's cached data (SWR's default cache is
// module-global), same reasoning as `Tarifas.test.tsx`'s own wrapper.
function wrapper({ children }: { children: ReactNode }): JSX.Element {
  const configValue = { provider: (): never => new Map() as never };
  return createElement(SWRConfig, { value: configValue }, children);
}

function renderResoluciones(uuidSucursal: string): ReturnType<typeof render> {
  return render(<ResolucionesDIAN uuidSucursal={uuidSucursal} />, { wrapper });
}

beforeEach(() => {
  mockedList.mockReset();
  mockedCreate.mockReset();
  mockedConsecutivo.mockReset();
  mockedConsecutivo.mockResolvedValue(null);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('ResolucionesDIAN', () => {
  it('RD1: lista vacía muestra el estado vacío, sin error', async () => {
    mockedList.mockResolvedValue({ items: [], nextCursor: null });
    renderResoluciones(SUCURSAL);
    await waitFor(() => {
      expect(screen.getByTestId('resolucion-empty')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('resolucion-error')).not.toBeInTheDocument();
  });

  it('RD2: lista con 1 resolución muestra sus campos de solo lectura', async () => {
    mockedList.mockResolvedValue({ items: [SAMPLE_RESOLUCION], nextCursor: null });
    renderResoluciones(SUCURSAL);
    const row = await screen.findByTestId(`resolucion-row-${SAMPLE_RESOLUCION.uuid}`);
    expect(row).toHaveTextContent('RES-0001');
    expect(screen.getByTestId('resolucion-numero')).toHaveTextContent('RES-0001');
    expect(screen.getByTestId('resolucion-prefijo')).toHaveTextContent('FE');
    expect(screen.getByTestId('resolucion-rango')).toHaveTextContent('1–5000');
    expect(screen.getByTestId('resolucion-fecha-inicio')).toHaveTextContent('2026-01-01');
    expect(screen.getByTestId('resolucion-fecha-fin')).toHaveTextContent('2027-01-01');
    expect(screen.getByTestId('resolucion-estado')).toHaveTextContent('activo');
    expect(screen.queryByTestId('resolucion-agotandose-banner')).not.toBeInTheDocument();
  });

  it('RD3: muestra el banner de agotamiento cuando consecutivo-actual reporta agotandose: true', async () => {
    mockedList.mockResolvedValue({ items: [SAMPLE_RESOLUCION], nextCursor: null });
    mockedConsecutivo.mockResolvedValue({
      consecutivo_actual: 4950,
      rango_hasta: 5000,
      restantes: 50,
      agotandose: true,
    });
    renderResoluciones(SUCURSAL);
    await screen.findByTestId(`resolucion-row-${SAMPLE_RESOLUCION.uuid}`);
    await waitFor(() => {
      expect(screen.getByTestId('resolucion-agotandose-banner')).toBeInTheDocument();
    });
    expect(mockedConsecutivo).toHaveBeenCalledWith(SAMPLE_RESOLUCION.uuid);
  });

  it('RD4: una lista vacía (equivalente a un 404 ya traducido por la capa API) nunca muestra error', async () => {
    // `listResolucionesFacturacion` ya traduce un 404 del recurso
    // cloud-only a `{ items: [], nextCursor: null }` (ver
    // `resolucionFacturacionApi.ts`) -- esta prueba fija el contrato desde
    // la perspectiva del componente: una lista vacía SIEMPRE es el estado
    // vacío, nunca el de error, sin importar la causa.
    mockedList.mockResolvedValue({ items: [], nextCursor: null });
    renderResoluciones(SUCURSAL);
    await waitFor(() => {
      expect(screen.getByTestId('resolucion-empty')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('resolucion-error')).not.toBeInTheDocument();
    expect(screen.queryByTestId('resolucion-loading')).not.toBeInTheDocument();
  });

  it('RD5: el flujo de creación llama createResolucionFacturacion y refresca la lista', async () => {
    mockedList
      .mockResolvedValueOnce({ items: [], nextCursor: null })
      .mockResolvedValueOnce({ items: [SAMPLE_RESOLUCION], nextCursor: null });
    mockedCreate.mockResolvedValue(SAMPLE_RESOLUCION);
    const user = userEvent.setup();
    renderResoluciones(SUCURSAL);
    await waitFor(() => screen.getByTestId('resolucion-empty'));

    await user.click(screen.getByTestId('resolucion-new'));
    expect(screen.getByTestId('resolucion-form')).toBeInTheDocument();

    await user.type(screen.getByTestId('resolucion-field-numero'), 'RES-0001');
    // `fecha_fin_vigencia` starts empty (no default) — type directly,
    // mirroring `ArqueosFilters.test.tsx`'s own `user.type` into an empty
    // `<input type="date">`.
    await user.type(screen.getByTestId('resolucion-field-fecha-fin'), '2027-01-01');
    await user.click(screen.getByTestId('resolucion-submit'));

    await waitFor(() => {
      expect(mockedCreate).toHaveBeenCalledWith(
        expect.objectContaining({ uuid_sucursal: SUCURSAL, numero_resolucion: 'RES-0001' }),
      );
    });
    await waitFor(() => {
      expect(screen.getByTestId(`resolucion-row-${SAMPLE_RESOLUCION.uuid}`)).toBeInTheDocument();
    });
    expect(screen.queryByTestId('resolucion-form')).not.toBeInTheDocument();
  });
});
