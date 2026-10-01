/**
 * `SucursalCaja.tsx` — tests (HU-F15.5, CU-13 completo).
 *
 * Two independent sections on one screen:
 *   - "Base y redondeo" (`configuracion_caja`, HU-F13.3 table): sourced
 *     via `useConfiguracionCajaEfectiva` (the real `.../efectiva` route).
 *   - "Tolerancias de arqueo" (`configuracion_tolerancias`): sourced via
 *     the EXISTING `useConfiguracionTolerancias` hook + the EXISTING
 *     `configuracionToleranciasApi` client (reused, not reimplemented —
 *     there's no `.../configuracion-tolerancias/efectiva` route).
 *
 * BR4 (ver/editar el default global cuando la sucursal no tiene
 * override propio):
 *   - Tolerancias: a real link to `/configuracion-tolerancias` (that
 *     admin screen already exists and already edits the global row).
 *   - Caja: no standalone global-config screen exists yet for this
 *     table (HU-F13.3 shipped only the backend + the `efectiva` route,
 *     no admin UI) — a new route/page is out of scope for this HU's
 *     explicit component list (`SucursalCaja.tsx` only). BR4 is
 *     fulfilled instead with an inline toggle that switches the SAME
 *     form between editing this branch's override and the global
 *     default (`uuid_sucursal: null`), without leaving the tab.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../../configuracion-caja/hooks/useConfiguracionCajaEfectiva', () => ({
  useConfiguracionCajaEfectiva: vi.fn(),
}));

vi.mock('../../configuracion-caja/api/configuracionCajaApi', () => ({
  createConfiguracionCaja: vi.fn(),
  updateConfiguracionCaja: vi.fn(),
}));

vi.mock('../../configuracion-tolerancias/hooks/useConfiguracionTolerancias', () => ({
  useConfiguracionTolerancias: vi.fn(),
}));

vi.mock('../../configuracion-tolerancias/api/configuracionToleranciasApi', () => ({
  createConfiguracionTolerancias: vi.fn(),
  updateConfiguracionTolerancias: vi.fn(),
}));

import { useConfiguracionCajaEfectiva } from '../../configuracion-caja/hooks/useConfiguracionCajaEfectiva';
import {
  createConfiguracionCaja,
  updateConfiguracionCaja,
} from '../../configuracion-caja/api/configuracionCajaApi';
import { useConfiguracionTolerancias } from '../../configuracion-tolerancias/hooks/useConfiguracionTolerancias';
import {
  createConfiguracionTolerancias,
  updateConfiguracionTolerancias,
} from '../../configuracion-tolerancias/api/configuracionToleranciasApi';
import { SucursalCaja } from './SucursalCaja';

const mockedUseCaja = useConfiguracionCajaEfectiva as ReturnType<typeof vi.fn>;
const mockedCreateCaja = createConfiguracionCaja as ReturnType<typeof vi.fn>;
const mockedUpdateCaja = updateConfiguracionCaja as ReturnType<typeof vi.fn>;
const mockedUseTolerancias = useConfiguracionTolerancias as ReturnType<typeof vi.fn>;
const mockedCreateTolerancias = createConfiguracionTolerancias as ReturnType<typeof vi.fn>;
const mockedUpdateTolerancias = updateConfiguracionTolerancias as ReturnType<typeof vi.fn>;

const SUCURSAL = 'cccccccc-1111-1111-1111-111111111111';

const CAJA_GLOBAL = {
  uuid: 'aaaaaaaa-0000-0000-0000-000000000000',
  uuid_sucursal: null,
  base_inicial_sugerida: '100000.0000',
  redondeo: '100',
  denominaciones_permitidas: [1000, 2000, 5000],
  vigente_desde: '2026-01-01T00:00:00',
  vigente_hasta: null,
  estado: 'activo',
  created_at: '2026-01-01T00:00:00',
  created_by: null,
  sync_status: 'sincronizado',
};

const CAJA_OVERRIDE = {
  ...CAJA_GLOBAL,
  uuid: 'bbbbbbbb-0000-0000-0000-000000000000',
  uuid_sucursal: SUCURSAL,
  base_inicial_sugerida: '150000.0000',
};

const TOLERANCIA_GLOBAL = {
  uuid: '11111111-1111-1111-1111-111111111111',
  uuid_sucursal: null,
  tolerancia_efectivo: '100.0000',
  tolerancia_datafono: '200.0000',
  vigente_desde: '2026-01-01T00:00:00',
  vigente_hasta: null,
  estado: 'activo',
  created_at: '2026-01-01T00:00:00',
  created_by: null,
  sync_status: 'sincronizado',
};

const TOLERANCIA_OVERRIDE = {
  ...TOLERANCIA_GLOBAL,
  uuid: '22222222-2222-2222-2222-222222222222',
  uuid_sucursal: SUCURSAL,
  tolerancia_efectivo: '50.0000',
};

function renderPage(): void {
  render(
    <MemoryRouter>
      <SucursalCaja uuidSucursal={SUCURSAL} />
    </MemoryRouter>,
  );
}

function tolerSinOverride(): void {
  mockedUseTolerancias.mockReturnValue({
    rows: [TOLERANCIA_GLOBAL],
    isLoading: false,
    error: undefined,
    refresh: vi.fn(),
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  tolerSinOverride();
  mockedUseCaja.mockReturnValue({
    data: CAJA_GLOBAL,
    isLoading: false,
    error: undefined,
    refresh: vi.fn(),
  });
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('SucursalCaja', () => {
  it('T1: loading state de la sección Caja', () => {
    mockedUseCaja.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: undefined,
      refresh: vi.fn(),
    });
    renderPage();
    expect(screen.getByTestId('sucursal-caja-base-loading')).toBeInTheDocument();
  });

  it('T2: override de Caja existente -> edita directo (sin link a global)', async () => {
    mockedUseCaja.mockReturnValue({
      data: CAJA_OVERRIDE,
      isLoading: false,
      error: undefined,
      refresh: vi.fn(),
    });
    renderPage();

    expect(screen.getByTestId('sucursal-caja-base-editing-override')).toBeInTheDocument();
    expect(screen.queryByTestId('sucursal-caja-base-toggle-global')).not.toBeInTheDocument();
    expect(screen.getByTestId('sucursal-caja-base-field-base-inicial')).toHaveValue(150000);

    mockedUpdateCaja.mockResolvedValueOnce(CAJA_OVERRIDE);
    await userEvent.click(screen.getByTestId('sucursal-caja-base-submit'));

    await waitFor(() => expect(mockedUpdateCaja).toHaveBeenCalledTimes(1));
    const [uuidArg, payloadArg] = mockedUpdateCaja.mock.calls[0]!;
    expect(uuidArg).toBe(CAJA_OVERRIDE.uuid);
    expect(payloadArg.uuid_sucursal).toBe(SUCURSAL);
  });

  it('T3: sin override de Caja -> muestra el efectivo global y permite crear un override', async () => {
    renderPage();

    expect(screen.getByTestId('sucursal-caja-base-sin-override')).toBeInTheDocument();
    expect(screen.getByTestId('sucursal-caja-base-toggle-global')).toBeInTheDocument();
    // Prefilled from the effective global value.
    expect(screen.getByTestId('sucursal-caja-base-field-base-inicial')).toHaveValue(100000);

    mockedCreateCaja.mockResolvedValueOnce(CAJA_OVERRIDE);
    await userEvent.click(screen.getByTestId('sucursal-caja-base-submit'));

    await waitFor(() => expect(mockedCreateCaja).toHaveBeenCalledTimes(1));
    expect(mockedCreateCaja.mock.calls[0]![0].uuid_sucursal).toBe(SUCURSAL);
  });

  it('T4: ni override ni default global -> mensaje explícito + toggle a "configurar default global"', async () => {
    mockedUseCaja.mockReturnValue({
      data: null,
      isLoading: false,
      error: undefined,
      refresh: vi.fn(),
    });
    renderPage();

    expect(screen.getByTestId('sucursal-caja-base-sin-configurar')).toBeInTheDocument();

    await userEvent.click(screen.getByTestId('sucursal-caja-base-toggle-global'));
    expect(screen.getByTestId('sucursal-caja-base-editing-global')).toBeInTheDocument();

    mockedCreateCaja.mockResolvedValueOnce(CAJA_GLOBAL);
    await userEvent.click(screen.getByTestId('sucursal-caja-base-submit'));

    await waitFor(() => expect(mockedCreateCaja).toHaveBeenCalledTimes(1));
    expect(mockedCreateCaja.mock.calls[0]![0].uuid_sucursal).toBeNull();
  });

  it('T5: denominaciones inválidas (no positivas) bloquean el submit (BR3)', async () => {
    renderPage();
    const field = screen.getByTestId('sucursal-caja-base-field-denominaciones');
    await userEvent.clear(field);
    await userEvent.type(field, '1000, -5, 0');
    await userEvent.click(screen.getByTestId('sucursal-caja-base-submit'));

    await waitFor(() => {
      expect(screen.getByTestId('sucursal-caja-base-denominaciones-error')).toBeInTheDocument();
    });
    expect(mockedCreateCaja).not.toHaveBeenCalled();
  });

  it('T6: override de Tolerancias existente -> edita directo (sin link a global)', async () => {
    mockedUseTolerancias.mockReturnValue({
      rows: [TOLERANCIA_GLOBAL, TOLERANCIA_OVERRIDE],
      isLoading: false,
      error: undefined,
      refresh: vi.fn(),
    });
    renderPage();

    expect(screen.getByTestId('sucursal-caja-tolerancias-editing-override')).toBeInTheDocument();
    expect(screen.queryByTestId('sucursal-caja-tolerancias-link-global')).not.toBeInTheDocument();

    mockedUpdateTolerancias.mockResolvedValueOnce(TOLERANCIA_OVERRIDE);
    await userEvent.click(screen.getByTestId('sucursal-caja-tolerancias-submit'));

    await waitFor(() => expect(mockedUpdateTolerancias).toHaveBeenCalledTimes(1));
    expect(mockedUpdateTolerancias.mock.calls[0]![0]).toBe(TOLERANCIA_OVERRIDE.uuid);
  });

  it('T7: sin override de Tolerancias -> link al default global + crea override prefilled', async () => {
    renderPage();

    const link = screen.getByTestId('sucursal-caja-tolerancias-link-global');
    expect(link).toHaveAttribute('href', '/configuracion-tolerancias');
    expect(screen.getByTestId('sucursal-caja-tolerancias-field-efectivo')).toHaveValue(100);

    mockedCreateTolerancias.mockResolvedValueOnce(TOLERANCIA_OVERRIDE);
    await userEvent.click(screen.getByTestId('sucursal-caja-tolerancias-submit'));

    await waitFor(() => expect(mockedCreateTolerancias).toHaveBeenCalledTimes(1));
    expect(mockedCreateTolerancias.mock.calls[0]![0].uuid_sucursal).toBe(SUCURSAL);
  });
});
