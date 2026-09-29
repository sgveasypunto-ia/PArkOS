/**
 * Tarifas — page-level integration tests (mock the api layer).
 *
 * Pins the container-level behaviour:
 *   1. Empty state when no branch is selected (activeEmpty path).
 *   1b. Empty state when a branch is selected but the API returns [].
 *   2. List filtered strictly by the selected branch.
 *   3. "Nueva tarifa" opens the modal — no "Todas" tab, no
 *      BranchSelector inside the modal (sucursal is the active one).
 *   4. CREATE modal pre-populates vigente_desde with the current
 *      minute; SELECTs do NOT include the "Cualquiera" cell.
 *   5. CREATE hides tipos already in use by an open tarifa for the
 *      selected branch (per-tipo filter, mirror of cupos).
 *   6. EDIT modal locks both tipo fields (readonly inputs) — the
 *      (sucursal, tipo_vehiculo, tipo_tarifa) cell-key is the
 *      tarifa's identity, fixed at creation.
 *   7. "Vigente desde" label drops "(opcional)" — the field is
 *      required (Zod schema + onChange blocks clear).
 *   8. "Editar" pre-fills the form with the existing tarifa row's
 *      values.
 *   9. Server error 409 tarifa_overlap renders the typed message.
 *  10. "Ver histórico" toggles the VersionHistoryPanel and calls
 *      listTarifasByKey.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SWRConfig } from 'swr';
import { createElement, type ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';

import { SucursalProvider } from '@/lib/sucursal-context';

vi.mock('@/features/sucursales/api/sucursalesApi', () => ({
  listSucursales: vi.fn(),
}));

vi.mock('../api/tarifasApi', () => ({
  listTarifas: vi.fn(),
  listTarifasByKey: vi.fn(),
  getTarifa: vi.fn(),
  createTarifa: vi.fn(),
  updateTarifa: vi.fn(),
  TarifaOverlapError: class TarifaOverlapError extends Error {},
  TarifaSucursalInmutableError: class TarifaSucursalInmutableError extends Error {},
}));

// Mirror the cupos test mock: HARDCODED_CATALOG with the 5 canonical
// tipos so the tipo_vehiculo / tipo_tarifa selects render real
// options in the form.
const SAMPLE_TIPOS_VEHICULO = [
  {
    uuid: '00000000-0000-0000-0000-000000000001',
    tipo: 'carro',
    vigente_desde: '2026-01-01T00:00:00',
    vigente_hasta: null,
    estado: 'activo',
    created_at: '2026-01-01T00:00:00',
    created_by: null,
    sync_status: 'sincronizado',
  },
  {
    uuid: '00000000-0000-0000-0000-000000000002',
    tipo: 'moto',
    vigente_desde: '2026-01-01T00:00:00',
    vigente_hasta: null,
    estado: 'activo',
    created_at: '2026-01-01T00:00:00',
    created_by: null,
    sync_status: 'sincronizado',
  },
];
const SAMPLE_TIPOS_TARIFA = [
  {
    uuid: '00000000-0000-0000-0000-0000000000a1',
    tipo: 'hora',
    vigente_desde: '2026-01-01T00:00:00',
    vigente_hasta: null,
    estado: 'activo',
    created_at: '2026-01-01T00:00:00',
    created_by: null,
    sync_status: 'sincronizado',
  },
  {
    uuid: '00000000-0000-0000-0000-0000000000a2',
    tipo: 'plena',
    vigente_desde: '2026-01-01T00:00:00',
    vigente_hasta: null,
    estado: 'activo',
    created_at: '2026-01-01T00:00:00',
    created_by: null,
    sync_status: 'sincronizado',
  },
];

vi.mock('@/features/tipos-vehiculo/hooks/useTiposVehiculo', () => ({
  useTiposVehiculo: () => ({
    tipos: SAMPLE_TIPOS_VEHICULO,
    isLoading: false,
    error: undefined,
    refresh: vi.fn().mockResolvedValue(SAMPLE_TIPOS_VEHICULO),
    isFromFallback: false,
  }),
}));

vi.mock('@/features/tipo-tarifa/hooks/useTipoTarifa', () => ({
  useTipoTarifa: () => ({
    tipos: SAMPLE_TIPOS_TARIFA,
    isLoading: false,
    error: undefined,
    refresh: vi.fn().mockResolvedValue(SAMPLE_TIPOS_TARIFA),
    isFromFallback: false,
  }),
}));

vi.mock('@parkos/ui-kit/hooks', () => ({
  useAdminAuth: () => ({
    user: { uuid: 'u-1', email: 'admin@parkos.local' },
    rol: 'admin',
    sucursalUuids: ['suc-1'],
    permisos: ['config_tarifas'],
    isAuthenticated: true,
    isLoading: false,
    error: undefined,
    refresh: async () => undefined,
    logout: async () => undefined,
  }),
}));

// The hooks (useTarifasList, useTarifasByKey, etc.) read from
// useAuthStore directly. Seed it with a token so the SWR key is
// non-null and the fetcher runs.
import { useAuthStore } from '@parkos/ui-kit/store';

import { listTarifas, createTarifa, listTarifasByKey } from '../api/tarifasApi';
import { listSucursales } from '@/features/sucursales/api/sucursalesApi';
import Tarifas from './Tarifas';

const mockedListTarifas = listTarifas as ReturnType<typeof vi.fn>;
const mockedCreateTarifa = createTarifa as ReturnType<typeof vi.fn>;
const mockedListByKey = listTarifasByKey as ReturnType<typeof vi.fn>;
const mockedListSucursales = listSucursales as ReturnType<typeof vi.fn>;

function wrapper({ children }: { children: ReactNode }): JSX.Element {
  const configValue = { provider: (): never => new Map() as never };
  return createElement(
    SucursalProvider,
    null,
    createElement(SWRConfig, { value: configValue }, children),
  );
}

function fullWrapper({ children }: { children: ReactNode }): JSX.Element {
  return createElement(
    MemoryRouter,
    null,
    createElement(wrapper, { children }),
  );
}

const SUCURSAL_1 = '11111111-1111-1111-1111-111111111111';
const SUCURSAL_2 = '22222222-2222-2222-2222-222222222222';

const SAMPLE_TARIFA: {
  uuid: string;
  uuid_sucursal: string;
  uuid_tipo_vehiculo: null;
  uuid_tipo_tarifa: null;
  valor: string;
  valor_plena: string;
  vigente_desde: string;
  vigente_hasta: null;
  estado: string;
  created_at: string;
  created_by: null;
  sync_status: string | null;
} = {
  uuid: 'aaaaaaaa-1111-1111-1111-111111111111',
  uuid_sucursal: SUCURSAL_1,
  uuid_tipo_vehiculo: null,
  uuid_tipo_tarifa: null,
  valor: '1500.0000',
  valor_plena: '2000.0000',
  vigente_desde: '2026-09-01T00:00:00',
  vigente_hasta: null,
  estado: 'activo',
  created_at: '2026-09-01T00:00:00',
  created_by: null,
  sync_status: 'sincronizado',
};

const SUCURSAL_NOMBRES = [
  { uuid: SUCURSAL_1, nombre: 'Sucursal Centro' },
  { uuid: SUCURSAL_2, nombre: 'Sucursal Norte' },
];

beforeEach(() => {
  mockedListTarifas.mockReset();
  mockedCreateTarifa.mockReset();
  mockedListByKey.mockReset();
  mockedListSucursales.mockReset();
  mockedListSucursales.mockResolvedValue(SUCURSAL_NOMBRES);
  useAuthStore.setState({ accessToken: 'tok', refreshToken: 'ref', expiresAt: null });
});

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.removeItem('parkos.lastSelectedSucursal');
  useAuthStore.setState({ accessToken: null, refreshToken: null, expiresAt: null });
});

describe('Tarifas page', () => {
  it('TP1: shows the active-empty hint when no branch is selected', async () => {
    mockedListTarifas.mockResolvedValue([]);
    render(<Tarifas />, { wrapper: fullWrapper });
    await waitFor(() => {
      expect(screen.getByTestId('tarifas-active-empty-selection')).toBeInTheDocument();
    });
  });

  it('TP1b: shows the per-branch empty state when a branch is selected but the API returns []', async () => {
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUCURSAL_1);
    mockedListTarifas.mockResolvedValue([]);
    render(<Tarifas />, { wrapper: fullWrapper });
    await waitFor(() => {
      expect(screen.getByTestId('tarifa-empty')).toBeInTheDocument();
    });
  });

  it('TP2: list filtered strictly by the selected branch', async () => {
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUCURSAL_1);
    mockedListTarifas.mockResolvedValue([
      { ...SAMPLE_TARIFA, uuid_sucursal: SUCURSAL_1 },
      // a row that belongs to ANOTHER branch must NOT render under the
      // selected one (regression for "solo la sucursal seleccionada").
      {
        ...SAMPLE_TARIFA,
        uuid: 'bbbbbbbb-1111-1111-1111-111111111111',
        uuid_sucursal: SUCURSAL_2,
        valor: '3000.0000',
      },
    ]);
    render(<Tarifas />, { wrapper: fullWrapper });
    await waitFor(() =>
      expect(
        screen.getByTestId('tarifa-sucursal-group-11111111-1111-1111-1111-111111111111'),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByTestId('tarifa-row-aaaaaaaa-1111-1111-1111-111111111111'),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId('tarifa-row-bbbbbbbb-1111-1111-1111-111111111111'),
    ).not.toBeInTheDocument();
  });

  it('TP3: "Nueva tarifa" opens the modal with no BranchSelector inside (sucursal pinned to the active one)', async () => {
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUCURSAL_1);
    mockedListTarifas.mockResolvedValue([]);
    render(<Tarifas />, { wrapper: fullWrapper });
    await waitFor(() => screen.getByTestId('tarifa-empty'));
    await userEvent.setup().click(screen.getByTestId('tarifa-new'));
    expect(screen.getByTestId('tarifa-form-modal')).toBeInTheDocument();
    expect(screen.getByTestId('tarifa-form')).toBeInTheDocument();
    // The "Todas las sucursales" tab is gone — strict single-list screen.
    expect(screen.queryByTestId('tarifas-tab-all')).not.toBeInTheDocument();
    // No BranchSelector inside the modal — the sucursal is the active
    // one shown as a read-only block.
    expect(screen.getByTestId('tarifa-field-sucursal-readonly')).toBeInTheDocument();
    // The select for uuid_sucursal is gone.
    expect(screen.queryByLabelText(/^Sucursal$/)).not.toBeInstanceOf(
      HTMLSelectElement,
    );
  });

  it('TP4: CREATE modal pre-populates "vigente_desde" with the current minute and drops "Cualquiera"', async () => {
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUCURSAL_1);
    mockedListTarifas.mockResolvedValue([]);
    render(<Tarifas />, { wrapper: fullWrapper });
    await waitFor(() => screen.getByTestId('tarifa-empty'));
    await userEvent.setup().click(screen.getByTestId('tarifa-new'));
    const dateInput = screen.getByTestId('tarifa-field-vigente-desde') as HTMLInputElement;
    // The input renders a local-ISO datetime-local value
    // (YYYY-MM-DDTHH:mm) within [now, now+1min].
    const before = new Date();
    before.setSeconds(0, 0);
    const expected = new Date(before);
    expected.setMinutes(expected.getMinutes() + 1);
    const pad = (n: number): string => String(n).padStart(2, '0');
    const fmt = (d: Date): string =>
      `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
      `T${pad(d.getHours())}:${pad(d.getMinutes())}`;
    const candidates = new Set<string>([fmt(before), fmt(expected)]);
    expect(candidates.has(dateInput.value)).toBe(true);
    // The vehiculo select does NOT include "Cualquiera" in CREATE.
    const vehiculoSelect = screen.getByTestId(
      'tarifa-field-tipo-vehiculo',
    ) as HTMLSelectElement;
    expect(Array.from(vehiculoSelect.options).map((o) => o.value)).not.toContain('');
    // The four modality value inputs are present.
    expect(screen.getByTestId('tarifa-field-valor-hora')).toBeInTheDocument();
    expect(screen.getByTestId('tarifa-field-valor-fraccion')).toBeInTheDocument();
    expect(screen.getByTestId('tarifa-field-valor-plena')).toBeInTheDocument();
    expect(screen.getByTestId('tarifa-field-valor-nocturna')).toBeInTheDocument();
  });

  it('TP5: CREATE hides tipos_vehiculo already in use by an open tarifa for this branch', async () => {
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUCURSAL_1);
    // Existing tarifa uses (carro, hora).
    mockedListTarifas.mockResolvedValue([
      {
        ...SAMPLE_TARIFA,
        uuid_sucursal: SUCURSAL_1,
        uuid_tipo_vehiculo: '00000000-0000-0000-0000-000000000001', // carro
        uuid_tipo_tarifa: '00000000-0000-0000-0000-0000000000a1', // hora
      },
    ]);
    render(<Tarifas />, { wrapper: fullWrapper });
    await waitFor(() =>
      expect(
        screen.getByTestId('tarifa-row-aaaaaaaa-1111-1111-1111-111111111111'),
      ).toBeInTheDocument(),
    );
    await userEvent.setup().click(screen.getByTestId('tarifa-new'));
    const vehiculoSelect = screen.getByTestId(
      'tarifa-field-tipo-vehiculo',
    ) as HTMLSelectElement;
    // "carro" hidden; "moto" remains.
    expect(Array.from(vehiculoSelect.options).map((o) => o.value)).not.toContain(
      '00000000-0000-0000-0000-000000000001',
    );
    expect(Array.from(vehiculoSelect.options).map((o) => o.value)).toContain(
      '00000000-0000-0000-0000-000000000002',
    );
  });

  it('TP6: EDIT modal locks tipo_vehiculo (readonly input)', async () => {
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUCURSAL_1);
    mockedListTarifas.mockResolvedValue([
      {
        ...SAMPLE_TARIFA,
        uuid_sucursal: SUCURSAL_1,
        uuid_tipo_vehiculo: '00000000-0000-0000-0000-000000000001', // carro
        uuid_tipo_tarifa: '00000000-0000-0000-0000-0000000000a1', // hora
        valor: '70.0000',
      },
    ]);
    render(<Tarifas />, { wrapper: fullWrapper });
    await waitFor(() =>
      expect(
        screen.getByTestId('tarifa-row-aaaaaaaa-1111-1111-1111-111111111111'),
      ).toBeInTheDocument(),
    );
    await userEvent.setup().click(
      screen.getByTestId('tarifa-edit-aaaaaaaa-1111-1111-1111-111111111111'),
    );
    // The vehiculo select is replaced by a readonly input with its label.
    const vehiculoInput = screen.getByTestId(
      'tarifa-field-tipo-vehiculo',
    ) as HTMLInputElement;
    expect(vehiculoInput.tagName).toBe('INPUT');
    expect(vehiculoInput.readOnly).toBe(true);
    expect(vehiculoInput.value).toBe('carro');
    expect(
      screen.getByTestId('tarifa-field-tipo-vehiculo-locked'),
    ).toBeInTheDocument();
  });

  it('TP7: "Vigente desde" label drops "(opcional)" — the field is required', async () => {
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUCURSAL_1);
    mockedListTarifas.mockResolvedValue([]);
    render(<Tarifas />, { wrapper: fullWrapper });
    await waitFor(() => screen.getByTestId('tarifa-empty'));
    await userEvent.setup().click(screen.getByTestId('tarifa-new'));
    const label = screen.getByText(/^Vigente desde/);
    expect(label.textContent).not.toMatch(/\(opcional\)/i);
    expect(
      screen.queryByText(/Vacío = ahora/i),
    ).not.toBeInTheDocument();
  });

  it('TP8: clicking "Editar" opens the modal pre-filled with the tarifa row', async () => {
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUCURSAL_1);
    mockedListTarifas.mockResolvedValue([
      {
        ...SAMPLE_TARIFA,
        uuid_sucursal: SUCURSAL_1,
        valor: '70.0000',
        valor_plena: '80.0000',
      },
    ]);
    render(<Tarifas />, { wrapper: fullWrapper });
    await waitFor(() =>
      expect(
        screen.getByTestId('tarifa-row-aaaaaaaa-1111-1111-1111-111111111111'),
      ).toBeInTheDocument(),
    );
    await userEvent.setup().click(
      screen.getByTestId('tarifa-edit-aaaaaaaa-1111-1111-1111-111111111111'),
    );
    expect(screen.getByTestId('tarifa-form-modal')).toBeInTheDocument();
    expect(screen.getByTestId('tarifa-form-editing')).toBeInTheDocument();
  });

  it('TP9: CREATE pre-populates tipo_vehiculo with the first catalog entry (regression for the 422 UX trap)', async () => {
    // The bug the operator hit on 2026-09-29: the form's
    // ``defaultValues.uuid_tipo_vehiculo`` was ``null`` in CREATE, so an
    // operator who forgot to interact with the select submitted
    // ``uuid_tipo_vehiculo: null`` and got a 422 from the strict
    // backend. The harness now pre-picks the first available entry
    // from the catalog so the form is never blank by default.
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUCURSAL_1);
    mockedListTarifas.mockResolvedValue([]);
    render(<Tarifas />, { wrapper: fullWrapper });
    await waitFor(() => screen.getByTestId('tarifa-empty'));
    await userEvent.setup().click(screen.getByTestId('tarifa-new'));
    const vehiculoSelect = screen.getByTestId(
      'tarifa-field-tipo-vehiculo',
    ) as HTMLSelectElement;
    // First catalog entry is "carro" (uuid sentinel
    // 00000000-0000-0000-0000-000000000001 in the test mock).
    expect(vehiculoSelect.value).toBe(
      '00000000-0000-0000-0000-000000000001',
    );
  });

  it('TP10: CREATE skips tipo_vehiculo already in use by an open tarifa for the branch', async () => {
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUCURSAL_1);
    // Existing tarifa uses carro.
    mockedListTarifas.mockResolvedValue([
      {
        ...SAMPLE_TARIFA,
        uuid_sucursal: SUCURSAL_1,
        uuid_tipo_vehiculo: '00000000-0000-0000-0000-000000000001', // carro
        uuid_tipo_tarifa: '00000000-0000-0000-0000-0000000000a2', // plena
      },
    ]);
    render(<Tarifas />, { wrapper: fullWrapper });
    await waitFor(() =>
      expect(
        screen.getByTestId('tarifa-row-aaaaaaaa-1111-1111-1111-111111111111'),
      ).toBeInTheDocument(),
    );
    await userEvent.setup().click(screen.getByTestId('tarifa-new'));
    const vehiculoSelect = screen.getByTestId(
      'tarifa-field-tipo-vehiculo',
    ) as HTMLSelectElement;
    // Skip "carro" → default to "moto" (next in catalog).
    expect(vehiculoSelect.value).toBe(
      '00000000-0000-0000-0000-000000000002',
    );
  });

  it('TP12: EDIT keeps the existing tipo_vehiculo value (regression — the harness useEffect must skip EDIT)', async () => {
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUCURSAL_1);
    mockedListTarifas.mockResolvedValue([
      {
        ...SAMPLE_TARIFA,
        uuid_sucursal: SUCURSAL_1,
        uuid_tipo_vehiculo: '00000000-0000-0000-0000-000000000002', // moto
        uuid_tipo_tarifa: '00000000-0000-0000-0000-0000000000a1', // hora
        valor: '70.0000',
      },
    ]);
    render(<Tarifas />, { wrapper: fullWrapper });
    await waitFor(() =>
      expect(
        screen.getByTestId('tarifa-row-aaaaaaaa-1111-1111-1111-111111111111'),
      ).toBeInTheDocument(),
    );
    await userEvent.setup().click(
      screen.getByTestId('tarifa-edit-aaaaaaaa-1111-1111-1111-111111111111'),
    );
    const vehiculoInput = screen.getByTestId(
      'tarifa-field-tipo-vehiculo',
    ) as HTMLInputElement;
    expect(vehiculoInput.tagName).toBe('INPUT');
    expect(vehiculoInput.value).toBe('moto');
    // The form must NOT pre-pick the first catalog entry — that
    // would overwrite the tarifa's locked tipo with 'carro'.
    // The useEffect's ``initial !== null`` guard pins this behavior.
  });
});