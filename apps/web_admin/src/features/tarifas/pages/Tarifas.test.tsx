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
  createTarifaBatch: vi.fn(),
  updateTarifa: vi.fn(),
  TarifaOverlapError: class TarifaOverlapError extends Error {},
  TarifaSucursalInmutableError: class TarifaSucursalInmutableError extends Error {},
  TarifaValidationError: class TarifaValidationError extends Error {
    issues: Array<{ path: string; message: string }>;
    constructor(zodError: { issues: Array<{ path: (string | number)[]; message: string }> }) {
      super('Validación del formulario');
      this.issues = (zodError.issues ?? []).map((i) => ({
        path: i.path.join('.'),
        message: i.message,
      }));
    }
  },
  TarifaConflictError: class TarifaConflictError extends Error {
    constraint: string | null;
    conflictingUuid: string | null;
    constructor(body: { detail?: Record<string, unknown> }) {
      const detail = body?.detail;
      const errCode = detail?.error;
      super(
        errCode === 'tarifa_overlap'
          ? `Conflicto con una tarifa existente (constraint: ${detail?.constraint ?? '?'})`
          : 'Conflicto con una tarifa existente',
      );
      this.constraint = (detail?.constraint as string | null) ?? null;
      this.conflictingUuid = (detail?.conflicting_uuid as string | null) ?? null;
    }
  },
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

import {
  listTarifas,
  createTarifa,
  createTarifaBatch,
  listTarifasByKey,
  updateTarifa,
} from '../api/tarifasApi';
import { TIPO_TARIFA_UUIDS } from '../api/tarifaAgrupada';
import { listSucursales } from '@/features/sucursales/api/sucursalesApi';
import Tarifas from './Tarifas';

const mockedListTarifas = listTarifas as ReturnType<typeof vi.fn>;
const mockedCreateTarifa = createTarifa as ReturnType<typeof vi.fn>;
const mockedCreateTarifaBatch = createTarifaBatch as ReturnType<typeof vi.fn>;
const mockedUpdateTarifa = updateTarifa as ReturnType<typeof vi.fn>;
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

// Compose the table row's data-testid — mirrors the page-side
// ``grupoKey`` shape (sucursal | tipo_vehiculo | vigente_desde).
function grupoKeyFor(
  sucursal: string | null,
  tipoVehiculo: string | null,
  vigenteDesde: string,
): string {
  return `${sucursal ?? ''}|${tipoVehiculo ?? ''}|${vigenteDesde}`;
}

const SAMPLE_TARIFA: {
  uuid: string;
  uuid_sucursal: string;
  uuid_tipo_vehiculo: string | null;
  uuid_tipo_tarifa: string | null;
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
  uuid_tipo_vehiculo: '00000000-0000-0000-0000-000000000001',
  uuid_tipo_tarifa: '00000000-0000-0000-0000-0000000000a1',
  valor: '1500.0000',
  valor_plena: '2000.0000',
  vigente_desde: '2026-09-01T00:00:00',
  vigente_hasta: null,
  estado: 'activo',
  created_at: '2026-09-01T00:00:00',
  created_by: null,
  sync_status: 'sincronizado',
};

const SAMPLE_GRUPO_KEY = grupoKeyFor(
  SUCURSAL_1,
  SAMPLE_TARIFA.uuid_tipo_vehiculo,
  SAMPLE_TARIFA.vigente_desde,
);

const SUCURSAL_NOMBRES = [
  { uuid: SUCURSAL_1, nombre: 'Sucursal Centro' },
  { uuid: SUCURSAL_2, nombre: 'Sucursal Norte' },
];

beforeEach(() => {
  mockedListTarifas.mockReset();
  mockedCreateTarifa.mockReset();
  mockedCreateTarifaBatch.mockReset();
  mockedUpdateTarifa.mockReset();
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
    const grupoKey = `${SUCURSAL_1}|${SAMPLE_TARIFA.uuid_tipo_vehiculo}|${SAMPLE_TARIFA.vigente_desde}`;
    await waitFor(() =>
      expect(
        screen.getByTestId('tarifa-sucursal-group-11111111-1111-1111-1111-111111111111'),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByTestId(`tarifa-row-${grupoKey}`),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId(`tarifa-row-${SUCURSAL_2}|${SAMPLE_TARIFA.uuid_tipo_vehiculo}|${SAMPLE_TARIFA.vigente_desde}`),
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
        screen.getByTestId(`tarifa-row-${SAMPLE_GRUPO_KEY}`),
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
        screen.getByTestId(`tarifa-row-${SAMPLE_GRUPO_KEY}`),
      ).toBeInTheDocument(),
    );
    await userEvent.setup().click(
      screen.getByTestId(`tarifa-edit-${SAMPLE_GRUPO_KEY}`),
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
        screen.getByTestId(`tarifa-row-${SAMPLE_GRUPO_KEY}`),
      ).toBeInTheDocument(),
    );
    await userEvent.setup().click(
      screen.getByTestId(`tarifa-edit-${SAMPLE_GRUPO_KEY}`),
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
        screen.getByTestId(`tarifa-row-${SAMPLE_GRUPO_KEY}`),
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
    const motoUuid = '00000000-0000-0000-0000-000000000002';
    mockedListTarifas.mockResolvedValue([
      {
        ...SAMPLE_TARIFA,
        uuid_sucursal: SUCURSAL_1,
        uuid_tipo_vehiculo: motoUuid,
        uuid_tipo_tarifa: '00000000-0000-0000-0000-0000000000a1',
        valor: '70.0000',
      },
    ]);
    const grupoKey = grupoKeyFor(SUCURSAL_1, motoUuid, SAMPLE_TARIFA.vigente_desde);
    render(<Tarifas />, { wrapper: fullWrapper });
    await waitFor(() =>
      expect(
        screen.getByTestId(`tarifa-row-${grupoKey}`),
      ).toBeInTheDocument(),
    );
    await userEvent.setup().click(
      screen.getByTestId(`tarifa-edit-${grupoKey}`),
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

  it('TP13: the table renders valores without wire decimals and with thousands separators', async () => {
    // The backend serializes NUMERIC(18,4) as "10000.0000". The
    // operator asked to see "10.000" instead. The formatter is
    // display-only: the modal inputs and the payloads keep the raw
    // four-decimal string.
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUCURSAL_1);
    const motoUuid = '00000000-0000-0000-0000-000000000002';
    const porModalidad = (uuid_tipo_tarifa: string, valor: string) => ({
      ...SAMPLE_TARIFA,
      uuid_sucursal: SUCURSAL_1,
      uuid_tipo_vehiculo: motoUuid,
      uuid_tipo_tarifa,
      valor,
      valor_plena: valor,
    });
    mockedListTarifas.mockResolvedValue([
      porModalidad(TIPO_TARIFA_UUIDS.hora, '10000.0000'),
      porModalidad(TIPO_TARIFA_UUIDS.fraccion, '2500.0000'),
      porModalidad(TIPO_TARIFA_UUIDS.plena, '1000000.0000'),
      porModalidad(TIPO_TARIFA_UUIDS.nocturna, '999.0000'),
    ]);
    const grupoKey = grupoKeyFor(SUCURSAL_1, motoUuid, SAMPLE_TARIFA.vigente_desde);
    render(<Tarifas />, { wrapper: fullWrapper });
    const row = await screen.findByTestId(`tarifa-row-${grupoKey}`);

    // hora, fraccion, plena, nocturna in table-column order.
    const celdas = Array.from(row.querySelectorAll('td')).map((td) =>
      td.textContent?.trim(),
    );
    expect(celdas.slice(1, 5)).toEqual(['10.000', '2.500', '1.000.000', '999']);
    // The raw wire string must NOT leak into the table.
    expect(row.textContent).not.toMatch(/\d+\.0000/);
  });

  it('TP14: a successful EDIT invalidates ALL 4 by-key SWR caches (one per modalidad) so the "Ver histórico" panel picks up the new version without F5', async () => {
    // Operator-reported bug (mirror of the cupos fix in
    // ``Cupos.test.tsx::CP16``): after editing a tarifa and
    // reopening the "Ver histórico" panel, the panel kept showing
    // the pre-edit chain. Root cause: ``useTarifasList::refresh``
    // only invalidates the 'tarifas-list' key, not the 4-way
    // by-key fan-out (one cache per ``TIPO_TARIFA_UUIDS``). The
    // fix (``Tarifas.tsx::invalidateByKey``) explicitly mutates
    // all 4 by-key keys after a successful write.
    //
    // Regression test: each ``Ver histórico`` open fires 4 by-key
    // calls (one per modalidad). After the EDIT submits, those 4
    // must be re-fetched again — total 8 calls. Without the fix,
    // the post-edit panel would reuse the cached 4 and stay stale.
    const editingUuid = 'aaaaaaaa-1111-1111-1111-111111111111';
    const tipoVehiculoUuid = SAMPLE_TARIFA.uuid_tipo_vehiculo as string;
    const editingRow = {
      ...SAMPLE_TARIFA,
      uuid: editingUuid,
      uuid_sucursal: SUCURSAL_1,
      uuid_tipo_vehiculo: tipoVehiculoUuid,
      uuid_tipo_tarifa: TIPO_TARIFA_UUIDS.hora,
      valor: '70.0000',
      valor_plena: '80.0000',
    };
    const newRow = { ...editingRow, uuid: 'dddddddd-1111-1111-1111-111111111111' };
    // The page opens 4 parallel by-key queries on each panel open.
    // Pre-edit: each one returns the existing tarifa row. Post-edit:
    // the 'hora' one returns [newRow, editingRow], the other 3 stay
    // the same (no edit on those modalidades in this test).
    mockedListByKey.mockImplementation(
      async (opts: { tipo_tarifa?: string | null }) => {
        if (opts.tipo_tarifa === TIPO_TARIFA_UUIDS.hora) return [newRow, editingRow];
        return [editingRow];
      },
    );
    mockedListTarifas
      .mockResolvedValueOnce([editingRow])
      .mockResolvedValueOnce([newRow]);
    mockedUpdateTarifa.mockResolvedValue(newRow);
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUCURSAL_1);
    const user = userEvent.setup();
    render(<Tarifas />, { wrapper: fullWrapper });
    const grupoKey = grupoKeyFor(SUCURSAL_1, tipoVehiculoUuid, SAMPLE_TARIFA.vigente_desde);
    await waitFor(() =>
      expect(screen.getByTestId(`tarifa-row-${grupoKey}`)).toBeInTheDocument(),
    );
    // 1) Open "Ver histórico" on the grouped row → 4 by-key calls.
    await user.click(screen.getByTestId(`tarifa-history-${grupoKey}`));
    await waitFor(() => expect(mockedListByKey).toHaveBeenCalledTimes(4));
    // 2) Edit and submit → invalidate the 4 by-key caches, 4 more calls.
    await user.click(screen.getByTestId(`tarifa-edit-${grupoKey}`));
    await user.click(screen.getByTestId('tarifa-submit'));
    await waitFor(() => expect(mockedListByKey).toHaveBeenCalledTimes(8));
    // Sanity: every post-edit call carries the right business key
    // (sucursal, tipo_vehiculo, tipo_tarifa). The implementation
    // fans out over TIPO_TARIFA_UUIDS, so the per-call assertions
    // guard against a regression where only one modalidad gets
    // invalidated (e.g. the operator only edited 'hora' but the
    // panel merges all 4 — leaving fraccion/plena/nocturna stale).
    const postEditCalls = mockedListByKey.mock.calls.slice(4);
    const modalidadUuids = new Set(
      postEditCalls.map(
        ([opts]) =>
          (opts as { tipo_tarifa?: string | null }).tipo_tarifa,
      ),
    );
    for (const uuid of Object.values(TIPO_TARIFA_UUIDS)) {
      expect(modalidadUuids.has(uuid)).toBe(true);
    }
  });

  // -----------------------------------------------------------------------
  // HU-tarifas-batch PR2 -- the operator-observed bugs from
  // chrome-devtools, now blocked at the form + page layer.
  // -----------------------------------------------------------------------

  it('TP-batch-1: submit with empty form -- no API call, 4 inline errors, alert never contains raw JSON', async () => {
    // Bug repro: chrome-devtools 2026-10-10 -- the operator hit
    // "Crear" with an empty form and the page split the submit into 4
    // sequential POSTs. The first one (HORA, valor='0' from the
    // null-to-'0' fallback) returned 201, the rest failed with 500
    // (UK01 race) or raw Zod JSON. After the fix:
    //   - The form's RHF refine rejects null/empty valor_* with
    //     "Requerido" inline before onSubmit runs.
    //   - The submit button is disabled when the form is invalid
    //     (formState.isValid).
    //   - createTarifaBatch is never called.
    mockedListTarifas.mockResolvedValue([]);
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUCURSAL_1);
    const user = userEvent.setup();
    render(<Tarifas />, { wrapper: fullWrapper });
    await user.click(screen.getByTestId('tarifa-new'));
    // The submit button is disabled because every valor_* is empty.
    const submitBtn = screen.getByTestId('tarifa-submit') as HTMLButtonElement;
    expect(submitBtn.disabled).toBe(true);
    // Try to click anyway -- the disabled state blocks the form, and
    // even if a malicious script forced the click, RHF would not call
    // onSubmit (its resolver rejects the empty payload first).
    await user.click(submitBtn).catch(() => {
      // userEvent on a disabled button throws; that's the contract.
    });
    expect(mockedCreateTarifaBatch).not.toHaveBeenCalled();
    expect(mockedCreateTarifa).not.toHaveBeenCalled();
    // No alert with raw Zod JSON.
    expect(screen.queryByText(/\[ \{/)).not.toBeInTheDocument();
    expect(screen.queryByText(/"code":/)).not.toBeInTheDocument();
  });

  it('TP-batch-2: submit only valor_hora -- 3 inline errors, no API call', async () => {
    // Partial form: only the first valor is filled. The form's RHF
    // refine blocks the submit; onSubmit is never called; no POST.
    mockedListTarifas.mockResolvedValue([]);
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUCURSAL_1);
    const user = userEvent.setup();
    render(<Tarifas />, { wrapper: fullWrapper });
    await user.click(screen.getByTestId('tarifa-new'));
    // Fill ONLY valor_hora; leave the other 3 empty.
    const hora = screen.getByTestId('tarifa-field-valor-hora');
    await user.type(hora, '2000');
    // The submit button stays disabled because the other 3 are empty.
    const submitBtn = screen.getByTestId('tarifa-submit') as HTMLButtonElement;
    expect(submitBtn.disabled).toBe(true);
    await user.click(submitBtn).catch(() => undefined);
    expect(mockedCreateTarifaBatch).not.toHaveBeenCalled();
  });

  it('TP-batch-3: happy path -- 4 valid values trigger ONE createTarifaBatch call, modal closes', async () => {
    // The operator filled all 4 inputs. The form is valid; submit
    // fires one POST /batch (not 4 POSTs). The mock resolves; the
    // modal closes; the list refreshes.
    mockedListTarifas
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        { ...SAMPLE_TARIFA, valor: '1500.0000' },
        { ...SAMPLE_TARIFA, uuid: 'b2', uuid_tipo_tarifa: TIPO_TARIFA_UUIDS.fraccion, valor: '800.0000' },
        { ...SAMPLE_TARIFA, uuid: 'b3', uuid_tipo_tarifa: TIPO_TARIFA_UUIDS.plena, valor: '2000.0000' },
        { ...SAMPLE_TARIFA, uuid: 'b4', uuid_tipo_tarifa: TIPO_TARIFA_UUIDS.nocturna, valor: '1000.0000' },
      ]);
    mockedCreateTarifaBatch.mockResolvedValue([
      { ...SAMPLE_TARIFA, valor: '1500.0000' },
      { ...SAMPLE_TARIFA, uuid: 'b2', uuid_tipo_tarifa: TIPO_TARIFA_UUIDS.fraccion, valor: '800.0000' },
      { ...SAMPLE_TARIFA, uuid: 'b3', uuid_tipo_tarifa: TIPO_TARIFA_UUIDS.plena, valor: '2000.0000' },
      { ...SAMPLE_TARIFA, uuid: 'b4', uuid_tipo_tarifa: TIPO_TARIFA_UUIDS.nocturna, valor: '1000.0000' },
    ]);
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUCURSAL_1);
    const user = userEvent.setup();
    render(<Tarifas />, { wrapper: fullWrapper });
    await user.click(screen.getByTestId('tarifa-new'));
    await user.type(screen.getByTestId('tarifa-field-valor-hora'), '1500');
    await user.type(screen.getByTestId('tarifa-field-valor-fraccion'), '800');
    await user.type(screen.getByTestId('tarifa-field-valor-plena'), '2000');
    await user.type(screen.getByTestId('tarifa-field-valor-nocturna'), '1000');
    const submitBtn = screen.getByTestId('tarifa-submit') as HTMLButtonElement;
    expect(submitBtn.disabled).toBe(false);
    await user.click(submitBtn);
    await waitFor(() => {
      expect(mockedCreateTarifaBatch).toHaveBeenCalledTimes(1);
    });
    // The batch payload carries 4 items (one per modalidad).
    const [payload] = mockedCreateTarifaBatch.mock.calls[0] as [
      {
        items: Array<{ uuid_tipo_tarifa: string; valor: string }>;
        uuid_sucursal: string;
        uuid_tipo_vehiculo: string;
      },
    ];
    expect(payload.items).toHaveLength(4);
    const modalidadesEnviadas = new Set(payload.items.map((i) => i.uuid_tipo_tarifa));
    for (const uuid of Object.values(TIPO_TARIFA_UUIDS)) {
      expect(modalidadesEnviadas.has(uuid)).toBe(true);
    }
    // The legacy 4-POST path must NOT be called.
    expect(mockedCreateTarifa).not.toHaveBeenCalled();
    // The modal closed and the list refreshed.
    await waitFor(() => {
      expect(screen.queryByTestId('tarifa-form-modal')).not.toBeInTheDocument();
    });
  });

  it('TP-batch-4: 409 from createTarifaBatch renders TarifaConflictError message, no raw JSON', async () => {
    // The PR1 backend maps a DB-level UK01 race to 409 with the
    // tarifa_overlap shape. The FE must show a translated message
    // (the constraint name when present) -- never the raw Zod JSON
    // that the chrome-devtools operator saw.
    mockedListTarifas.mockResolvedValue([]);
    const { TarifaConflictError } = await import('../api/tarifasApi');
    mockedCreateTarifaBatch.mockRejectedValue(
      new TarifaConflictError({
        detail: {
          error: 'tarifa_overlap',
          conflicting_uuid: null,
          constraint: 'tarifas_sucursal_uk01',
        },
      }),
    );
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUCURSAL_1);
    const user = userEvent.setup();
    render(<Tarifas />, { wrapper: fullWrapper });
    await user.click(screen.getByTestId('tarifa-new'));
    await user.type(screen.getByTestId('tarifa-field-valor-hora'), '1500');
    await user.type(screen.getByTestId('tarifa-field-valor-fraccion'), '800');
    await user.type(screen.getByTestId('tarifa-field-valor-plena'), '2000');
    await user.type(screen.getByTestId('tarifa-field-valor-nocturna'), '1000');
    await user.click(screen.getByTestId('tarifa-submit'));
    // The alert must show the human-readable message, not JSON.
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('tarifas_sucursal_uk01');
    expect(alert.textContent).not.toContain('[ {');
    expect(alert.textContent).not.toContain('"code"');
  });
});