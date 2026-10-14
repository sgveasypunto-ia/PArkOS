/**
 * Cupos — page-level integration tests (mock the api layer).
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

vi.mock('../api/cuposApi', () => ({
  listCupos: vi.fn(),
  listCuposByKey: vi.fn(),
  getCupo: vi.fn(),
  createCupo: vi.fn(),
  updateCupo: vi.fn(),
  // Mirror the real CantidadOverlapError shape so the page's
  // `mapError` branch (and its boundary-equality detection) can
  // read conflictingUuid / conflictingVigenteHasta off the
  // instance, exactly like the live module would.
  CantidadOverlapError: class CantidadOverlapError extends Error {
    conflictingUuid: string;
    conflictingVigenteDesde: string | null;
    conflictingVigenteHasta: string | null;
    constructor(body: {
      conflicting_uuid: string;
      conflicting_vigente_desde: string | null;
      conflicting_vigente_hasta: string | null;
    }) {
      super('overlap');
      this.name = 'CantidadOverlapError';
      this.conflictingUuid = body.conflicting_uuid;
      this.conflictingVigenteDesde = body.conflicting_vigente_desde;
      this.conflictingVigenteHasta = body.conflicting_vigente_hasta;
    }
  },
  CantidadBajoIngresosError: class CantidadBajoIngresosError extends Error {},
  CantidadSucursalInmutableError: class CantidadSucursalInmutableError extends Error {},
}));

vi.mock('@/features/tipos-vehiculo/api/tiposVehiculoApi', () => ({
  listTiposVehiculo: vi.fn().mockResolvedValue([]),
  createTipoVehiculo: vi.fn(),
}));

const SAMPLE_TIPOS = [
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
  {
    uuid: '00000000-0000-0000-0000-000000000003',
    tipo: 'bicicleta',
    vigente_desde: '2026-01-01T00:00:00',
    vigente_hasta: null,
    estado: 'activo',
    created_at: '2026-01-01T00:00:00',
    created_by: null,
    sync_status: 'sincronizado',
  },
  {
    uuid: '00000000-0000-0000-0000-000000000004',
    tipo: 'patineta',
    vigente_desde: '2026-01-01T00:00:00',
    vigente_hasta: null,
    estado: 'activo',
    created_at: '2026-01-01T00:00:00',
    created_by: null,
    sync_status: 'sincronizado',
  },
  {
    uuid: '00000000-0000-0000-0000-000000000005',
    tipo: 'otro',
    vigente_desde: '2026-01-01T00:00:00',
    vigente_hasta: null,
    estado: 'activo',
    created_at: '2026-01-01T00:00:00',
    created_by: null,
    sync_status: 'sincronizado',
  },
];

// Module-scoped mutable holder so per-test overrides (CP7 below) can
// shrink the catalog without re-mocking the module. Default: first two
// entries (carro, moto) — the prior tests assume this 2-item shape.
let __mockTipos = SAMPLE_TIPOS.slice(0, 2);

vi.mock('@/features/tipos-vehiculo/hooks/useTiposVehiculo', () => ({
  useTiposVehiculo: () => ({
    get tipos() {
      return __mockTipos;
    },
    isLoading: false,
    error: undefined,
    refresh: vi.fn().mockResolvedValue([]),
    isFromFallback: false,
  }),
}));

vi.mock('@parkos/ui-kit/hooks', () => ({
  useAdminAuth: () => ({
    user: { uuid: 'u-1', email: 'admin@parkos.local' },
    rol: 'admin',
    // CP19 + CP20 add a second branch (SUCURSAL_2) on top of the
    // canonical SUCURSAL_1, so the inline branch combobox stays
    // populated. The list of permitidas must include both UUIDs
    // for the client-side filter to keep them.
    sucursalUuids: [
      '11111111-1111-1111-1111-111111111111',
      '22222222-2222-2222-2222-222222222222',
    ],
    permisos: ['config_cupos'],
    isAuthenticated: true,
    isLoading: false,
    error: undefined,
    refresh: async () => undefined,
    logout: async () => undefined,
  }),
}));

import { listCupos, createCupo, updateCupo, listCuposByKey } from '../api/cuposApi';
import { listSucursales } from '@/features/sucursales/api/sucursalesApi';
import { useAuthStore } from '@parkos/ui-kit/store';
import Cupos from './Cupos';

const mockedListCupos = listCupos as ReturnType<typeof vi.fn>;
const mockedCreateCupo = createCupo as ReturnType<typeof vi.fn>;
const mockedUpdateCupo = updateCupo as ReturnType<typeof vi.fn>;
const mockedListByKey = listCuposByKey as ReturnType<typeof vi.fn>;
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
  return createElement(MemoryRouter, null, createElement(wrapper, { children }));
}

const SUCURSAL_1 = '11111111-1111-1111-1111-111111111111';

const SAMPLE_CUPO: {
  uuid: string;
  uuid_sucursal: string;
  uuid_tipo_vehiculo: null;
  cantidad: number;
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
  cantidad: 50,
  vigente_desde: '2026-09-01T00:00:00',
  vigente_hasta: null,
  estado: 'activo',
  created_at: '2026-09-01T00:00:00',
  created_by: null,
  sync_status: 'sincronizado',
};

beforeEach(() => {
  mockedListCupos.mockReset();
  mockedCreateCupo.mockReset();
  mockedUpdateCupo.mockReset();
  mockedListByKey.mockReset();
  mockedListSucursales.mockReset();
  mockedListSucursales.mockResolvedValue([
    { uuid: SUCURSAL_1, nombre: 'Sucursal Centro', prefijo_nombre: 'CEN' },
  ]);
  useAuthStore.setState({ accessToken: 'tok', refreshToken: 'ref', expiresAt: null });
});

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.removeItem('parkos.lastSelectedSucursal');
  useAuthStore.setState({ accessToken: null, refreshToken: null, expiresAt: null });
});

describe('Cupos page', () => {
  it('CP1: empty state when no branch is selected', async () => {
    mockedListCupos.mockResolvedValue([]);
    render(<Cupos />, { wrapper: fullWrapper });
    await waitFor(() => {
      expect(screen.getByTestId('cupos-active-empty-selection')).toBeInTheDocument();
    });
  });

  it('CP1b: empty state when a branch is selected but the API returns []', async () => {
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUCURSAL_1);
    mockedListCupos.mockResolvedValue([]);
    render(<Cupos />, { wrapper: fullWrapper });
    await waitFor(() => {
      expect(screen.getByTestId('cupo-empty')).toBeInTheDocument();
    });
  });

  it('CP2: list filtered strictly by the selected branch', async () => {
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUCURSAL_1);
    mockedListCupos.mockResolvedValue([
      { ...SAMPLE_CUPO, uuid_sucursal: SUCURSAL_1, cantidad: 50 },
      // a row that belongs to ANOTHER branch must NOT render under the
      // selected one (regression for "solo la sucursal seleccionada").
      {
        ...SAMPLE_CUPO,
        uuid: 'bbbbbbbb-1111-1111-1111-111111111111',
        uuid_sucursal: '99999999-9999-9999-9999-999999999999',
        cantidad: 99,
      },
    ]);
    render(<Cupos />, { wrapper: fullWrapper });
    await waitFor(() => {
      expect(
        screen.getByTestId('cupo-sucursal-group-11111111-1111-1111-1111-111111111111'),
      ).toBeInTheDocument();
    });
    expect(
      screen.getByTestId('cupo-row-aaaaaaaa-1111-1111-1111-111111111111'),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId('cupo-row-bbbbbbbb-1111-1111-1111-111111111111'),
    ).not.toBeInTheDocument();
  });

  it('CP3: "Nuevo cupo" opens the modal with an empty form (no "Todas" tab)', async () => {
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUCURSAL_1);
    mockedListCupos.mockResolvedValue([]);
    render(<Cupos />, { wrapper: fullWrapper });
    await waitFor(() => screen.getByTestId('cupo-empty'));
    await userEvent.setup().click(screen.getByTestId('cupo-new'));
    expect(screen.getByTestId('cupo-form-modal')).toBeInTheDocument();
    expect(screen.getByTestId('cupo-form')).toBeInTheDocument();
    // The "Todas las sucursales" tab is gone — strict single-list screen.
    expect(screen.queryByTestId('cupos-tab-all')).not.toBeInTheDocument();
  });

  it('CP4: clicking "Editar" opens the modal pre-filled with the cupo row', async () => {
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUCURSAL_1);
    mockedListCupos.mockResolvedValue([
      { ...SAMPLE_CUPO, uuid_sucursal: SUCURSAL_1, cantidad: 50 },
    ]);
    render(<Cupos />, { wrapper: fullWrapper });
    await waitFor(() =>
      expect(
        screen.getByTestId('cupo-row-aaaaaaaa-1111-1111-1111-111111111111'),
      ).toBeInTheDocument(),
    );
    await userEvent.setup().click(
      screen.getByTestId('cupo-edit-aaaaaaaa-1111-1111-1111-111111111111'),
    );
    expect(screen.getByTestId('cupo-form-modal')).toBeInTheDocument();
    const cantidad = screen.getByTestId('cupo-field-cantidad') as HTMLInputElement;
    expect(cantidad.value).toBe('50');
    expect(screen.getByTestId('cupo-form-editing')).toBeInTheDocument();
  });

  it('CP5: renders "Tipo de vehículo" column resolving uuid to name', async () => {
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUCURSAL_1);
    mockedListCupos.mockResolvedValue([
      {
        ...SAMPLE_CUPO,
        uuid_sucursal: SUCURSAL_1,
        cantidad: 10,
        uuid_tipo_vehiculo: '00000000-0000-0000-0000-000000000001',
      },
    ]);
    render(<Cupos />, { wrapper: fullWrapper });
    await waitFor(() =>
      expect(
        screen.getByTestId('cupo-tipo-aaaaaaaa-1111-1111-1111-111111111111'),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByTestId('cupo-tipo-aaaaaaaa-1111-1111-1111-111111111111').textContent,
    ).toBe('carro');
  });

  it('CP6: "Nuevo tipo" toggle reveals the inline sub-form inside the modal', async () => {
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUCURSAL_1);
    mockedListCupos.mockResolvedValue([]);
    render(<Cupos />, { wrapper: fullWrapper });
    await waitFor(() => screen.getByTestId('cupo-empty'));
    await userEvent.setup().click(screen.getByTestId('cupo-new'));
    expect(screen.queryByTestId('cupo-new-tipo-panel')).not.toBeInTheDocument();
    await userEvent.setup().click(screen.getByTestId('cupo-new-tipo-toggle'));
    expect(screen.getByTestId('cupo-new-tipo-panel')).toBeInTheDocument();
    expect(screen.getByTestId('cupo-new-tipo-input')).toBeInTheDocument();
  });

  it('CP7: hides "+ Nuevo tipo" toggle when the catalog is at the 5-tipo cap', async () => {
    // The mock returns all 5 canonical tipos by default for THIS test only.
    __mockTipos = SAMPLE_TIPOS;
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUCURSAL_1);
    mockedListCupos.mockResolvedValue([]);
    render(<Cupos />, { wrapper: fullWrapper });
    await waitFor(() => screen.getByTestId('cupo-empty'));
    await userEvent.setup().click(screen.getByTestId('cupo-new'));
    expect(screen.getByTestId('cupo-field-tipo-vehiculo')).toBeInTheDocument();
    expect(screen.queryByTestId('cupo-new-tipo-toggle')).not.toBeInTheDocument();
    __mockTipos = SAMPLE_TIPOS.slice(0, 2);
  });

  it('CP8: CREATE modal pre-populates "vigente_desde" with the current datetime', async () => {
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUCURSAL_1);
    mockedListCupos.mockResolvedValue([]);
    render(<Cupos />, { wrapper: fullWrapper });
    await waitFor(() => screen.getByTestId('cupo-empty'));
    await userEvent.setup().click(screen.getByTestId('cupo-new'));
    const dateInput = screen.getByTestId('cupo-field-vigente-desde') as HTMLInputElement;
    expect(dateInput).toBeInTheDocument();
    // The input renders a local-ISO datetime-local value (YYYY-MM-DDTHH:mm).
    // Tolerate a 1-minute skew vs ``new Date()`` so the test is stable
    // when the minute rolls over between the harness init and the assert.
    const before = new Date();
    before.setSeconds(0, 0);
    const expected = new Date(before);
    expected.setMinutes(expected.getMinutes() + 1);
    const pad = (n: number): string => String(n).padStart(2, '0');
    const fmt = (d: Date): string =>
      `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
      `T${pad(d.getHours())}:${pad(d.getMinutes())}`;
    const candidates = new Set<string>([fmt(before), fmt(expected)]);
    // The input is populated with the current local minute (or the next
    // one if the test crossed a minute boundary mid-run).
    expect(candidates.has(dateInput.value)).toBe(true);
  });

  it('CP9: EDIT modal defaults "vigente_desde" to current time + 1 minute', async () => {
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUCURSAL_1);
    mockedListCupos.mockResolvedValue([
      {
        ...SAMPLE_CUPO,
        uuid_sucursal: SUCURSAL_1,
        cantidad: 50,
        // The existing row's vigente_desde is in the past; EDIT default
        // should ignore it and use now + 1min (canonical UX rule).
        vigente_desde: '2020-01-01T00:00:00',
      },
    ]);
    render(<Cupos />, { wrapper: fullWrapper });
    await waitFor(() =>
      expect(
        screen.getByTestId('cupo-row-aaaaaaaa-1111-1111-1111-111111111111'),
      ).toBeInTheDocument(),
    );
    await userEvent.setup().click(
      screen.getByTestId('cupo-edit-aaaaaaaa-1111-1111-1111-111111111111'),
    );
    const dateInput = screen.getByTestId('cupo-field-vigente-desde') as HTMLInputElement;
    // Expected: now in YYYY-MM-DDTHH:mm (local) within [now, now+2min].
    // Tolerate a 2-minute skew vs ``new Date()`` so the test is stable
    // when the minute rolls over between the harness init and the assert.
    const pad = (n: number): string => String(n).padStart(2, '0');
    const fmt = (d: Date): string =>
      `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
      `T${pad(d.getHours())}:${pad(d.getMinutes())}`;
    const candidates = new Set<string>();
    for (let offset = 0; offset <= 2; offset += 1) {
      const d = new Date();
      d.setSeconds(0, 0);
      d.setMinutes(d.getMinutes() + offset);
      candidates.add(fmt(d));
    }
    // 2020-01-01T00:00 must NOT appear (existing row's value).
    expect(dateInput.value).not.toBe('2020-01-01T00:00');
    // The input is populated with the current local minute +1
    // (or the next minute if the test crossed a boundary mid-run).
    expect(candidates.has(dateInput.value)).toBe(true);
  });

  it('CP10: CREATE modal hides tipos already in use by an open cupo for this branch', async () => {
    // Mock returns the full 5-tipocatalog AND a cupo for (sucursal, 'carro').
    __mockTipos = SAMPLE_TIPOS;
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUCURSAL_1);
    mockedListCupos.mockResolvedValue([
      {
        ...SAMPLE_CUPO,
        uuid_sucursal: SUCURSAL_1,
        uuid_tipo_vehiculo: '00000000-0000-0000-0000-000000000001', // carro
        cantidad: 50,
      },
    ]);
    render(<Cupos />, { wrapper: fullWrapper });
    await waitFor(() => screen.getByTestId('cupo-empty'));
    await userEvent.setup().click(screen.getByTestId('cupo-new'));
    const select = screen.getByTestId(
      'cupo-field-tipo-vehiculo',
    ) as HTMLSelectElement;
    const optionValues = Array.from(select.options).map((o) => o.value);
    // "carro" is hidden; the other 4 remain. CREATE no longer offers
    // the "Cualquiera" cell (uuid_tipo_vehiculo = null) — every cupo
    // must target a specific tipo from the catalog.
    expect(optionValues).not.toContain('00000000-0000-0000-0000-000000000001');
    expect(optionValues).toContain('00000000-0000-0000-0000-000000000002'); // moto
    expect(optionValues).toContain('00000000-0000-0000-0000-000000000003'); // bicicleta
    expect(optionValues).toContain('00000000-0000-0000-0000-000000000004'); // patineta
    expect(optionValues).toContain('00000000-0000-0000-0000-000000000005'); // otro
    expect(optionValues).not.toContain(''); // Cualquiera gone in CREATE
    __mockTipos = SAMPLE_TIPOS.slice(0, 2);
  });

  it('CP11: EDIT modal locks the tipo field (cannot change it after creation)', async () => {
    __mockTipos = SAMPLE_TIPOS;
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUCURSAL_1);
    mockedListCupos.mockResolvedValue([
      {
        ...SAMPLE_CUPO,
        uuid_sucursal: SUCURSAL_1,
        uuid_tipo_vehiculo: '00000000-0000-0000-0000-000000000001', // carro
        cantidad: 50,
      },
    ]);
    render(<Cupos />, { wrapper: fullWrapper });
    await waitFor(() =>
      expect(
        screen.getByTestId('cupo-row-aaaaaaaa-1111-1111-1111-111111111111'),
      ).toBeInTheDocument(),
    );
    await userEvent.setup().click(
      screen.getByTestId('cupo-edit-aaaaaaaa-1111-1111-1111-111111111111'),
    );
    // No <select>; the tipo is rendered as a readonly input with the
    // label as its value. The locked-hint is also visible.
    expect(screen.queryByTestId('cupo-field-tipo-vehiculo')).not.toBeInstanceOf(
      HTMLSelectElement,
    );
    const lockedInput = screen.getByTestId(
      'cupo-field-tipo-vehiculo',
    ) as HTMLInputElement;
    expect(lockedInput.readOnly).toBe(true);
    expect(lockedInput.value).toBe('carro');
    expect(screen.getByTestId('cupo-field-tipo-vehiculo-locked')).toBeInTheDocument();
    __mockTipos = SAMPLE_TIPOS.slice(0, 2);
  });

  it('CP12: CREATE modal never offers "Cualquiera" — every cupo must target a specific tipo', async () => {
    // Even when no cupo exists yet, the CREATE select must not surface a
    // uuid_tipo_vehiculo=null option. Every cupo created from this UI
    // carries a non-null uuid_tipo_vehiculo.
    __mockTipos = SAMPLE_TIPOS;
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUCURSAL_1);
    mockedListCupos.mockResolvedValue([]);
    render(<Cupos />, { wrapper: fullWrapper });
    await waitFor(() => screen.getByTestId('cupo-empty'));
    await userEvent.setup().click(screen.getByTestId('cupo-new'));
    const select = screen.getByTestId(
      'cupo-field-tipo-vehiculo',
    ) as HTMLSelectElement;
    const optionValues = Array.from(select.options).map((o) => o.value);
    expect(optionValues).not.toContain(''); // Cualquiera gone from CREATE
    // All 5 canonical tipos are available.
    for (const tv of SAMPLE_TIPOS) {
      expect(optionValues).toContain(tv.uuid);
    }
    __mockTipos = SAMPLE_TIPOS.slice(0, 2);
  });

  it('CP13: "vigente_desde" label drops "(opcional)" — the field is required', async () => {
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUCURSAL_1);
    mockedListCupos.mockResolvedValue([]);
    render(<Cupos />, { wrapper: fullWrapper });
    await waitFor(() => screen.getByTestId('cupo-empty'));
    await userEvent.setup().click(screen.getByTestId('cupo-new'));
    // Label text no longer contains "(opcional)".
    const label = screen.getByText(/^Vigente desde/);
    expect(label.textContent).not.toMatch(/\(opcional\)/i);
    // Help text no longer mentions "Vacío = ahora".
    expect(
      screen.queryByText(/Vacío = ahora/i),
    ).not.toBeInTheDocument();
  });

  it('CP14: CREATE auto-selects the first available tipo so the payload never carries uuid_tipo_vehiculo=null', async () => {
    // Regression for the operator-reported bug: the browser visually
    // shows the first <option> in the filtered select, but the RHF
    // state stayed null and the submitted payload carried
    // uuid_tipo_vehiculo=null, persisting the cupo as the
    // "Cualquiera" cell instead of the tipo the operator picked. Two
    // tipos already in use (carro, moto) so the first available is
    // bicicleta — that's the uuid the payload must carry.
    __mockTipos = SAMPLE_TIPOS;
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUCURSAL_1);
    mockedListCupos.mockResolvedValue([
      {
        ...SAMPLE_CUPO,
        uuid_sucursal: SUCURSAL_1,
        uuid_tipo_vehiculo: '00000000-0000-0000-0000-000000000001', // carro
        cantidad: 50,
      },
      {
        ...SAMPLE_CUPO,
        uuid: 'cccccccc-1111-1111-1111-111111111111',
        uuid_sucursal: SUCURSAL_1,
        uuid_tipo_vehiculo: '00000000-0000-0000-0000-000000000002', // moto
        cantidad: 30,
      },
    ]);
    const createdRow = {
      ...SAMPLE_CUPO,
      uuid: 'dddddddd-1111-1111-1111-111111111111',
      uuid_sucursal: SUCURSAL_1,
      uuid_tipo_vehiculo: '00000000-0000-0000-0000-000000000003', // bicicleta
      cantidad: 10,
    };
    mockedCreateCupo.mockResolvedValue(createdRow);
    const user = userEvent.setup();
    render(<Cupos />, { wrapper: fullWrapper });
    await waitFor(() => screen.getByTestId('cupo-empty'));
    await user.click(screen.getByTestId('cupo-new'));
    // Do NOT touch the tipo select — the operator-reported bug was
    // exactly that case: user sees "bicicleta" visually, leaves the
    // select alone, and the form must not submit null.
    const cantidad = screen.getByTestId('cupo-field-cantidad') as HTMLInputElement;
    await user.clear(cantidad);
    await user.type(cantidad, '10');
    await user.click(screen.getByTestId('cupo-submit'));
    await waitFor(() => {
      expect(mockedCreateCupo).toHaveBeenCalledTimes(1);
    });
    const submitted = mockedCreateCupo.mock.calls[0]?.[0] as {
      uuid_tipo_vehiculo: string | null;
      cantidad: number;
    };
    expect(submitted.uuid_tipo_vehiculo).not.toBeNull();
    expect(submitted.uuid_tipo_vehiculo).toBe(
      '00000000-0000-0000-0000-000000000003', // bicicleta
    );
    expect(submitted.cantidad).toBe(10);
    __mockTipos = SAMPLE_TIPOS.slice(0, 2);
  });

  it('CP15: re-editing the same cupo with the boundary-equality 409 shows the specific message (not the generic "elegí otro instante")', async () => {
    // End-to-end: the operator re-edits a cupo with the SAME
    // vigente_desde the row already has, the backend returns
    // 409 cantidad_overlap with conflictingUuid == the row's
    // own uuid and conflictingVigenteHasta: null (boundary
    // equality, see empresa.py:1143 `<=`). The page's mapError
    // MUST detect the (editingUuid === conflictingUuid,
    // conflictingVigenteHasta === null) signal and render the
    // specific boundary-equality message — not the generic
    // fallback.
    __mockTipos = SAMPLE_TIPOS;
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUCURSAL_1);
    const editingUuid = '1a231f57-cb96-4284-b4b0-f3e7c594f631';
    const editingRow = {
      ...SAMPLE_CUPO,
      uuid: editingUuid,
      uuid_sucursal: SUCURSAL_1,
      uuid_tipo_vehiculo: '00000000-0000-0000-0000-000000000003', // bicicleta
      cantidad: 5,
      vigente_desde: '2026-10-09T22:35:00',
    };
    mockedListCupos.mockResolvedValue([editingRow]);
    // Surface the same 409 the operator reported in the live bug
    // report (cuposApi: 409 {error: cantidad_overlap,
    // conflicting_uuid, conflicting_vigente_desde, conflicting_vigente_hasta:null}).
    const overlapBody = {
      detail: {
        error: 'cantidad_overlap',
        conflicting_uuid: editingUuid,
        conflicting_vigente_desde: '2026-10-09T22:35:00',
        conflicting_vigente_hasta: null,
      },
    };
    const { CantidadOverlapError: COE } = await import('../api/cuposApi');
    mockedUpdateCupo.mockRejectedValue(
      new COE({
        conflicting_uuid: overlapBody.detail.conflicting_uuid,
        conflicting_vigente_desde: overlapBody.detail.conflicting_vigente_desde,
        conflicting_vigente_hasta: overlapBody.detail.conflicting_vigente_hasta,
      }),
    );
    const user = userEvent.setup();
    render(<Cupos />, { wrapper: fullWrapper });
    await waitFor(() =>
      expect(
        screen.getByTestId(`cupo-row-${editingUuid}`),
      ).toBeInTheDocument(),
    );
    await user.click(screen.getByTestId(`cupo-edit-${editingUuid}`));
    await user.click(screen.getByTestId('cupo-submit'));
    // The specific message MUST be rendered (not the generic
    // "La nueva ventana se solapa...").
    const specificMessage = await screen.findByText(
      /Estás editando con una fecha anterior o igual a la versión activa/i,
    );
    expect(specificMessage).toBeInTheDocument();
    // The generic fallback must NOT be present.
    expect(
      screen.queryByText(/La nueva ventana se solapa/i),
    ).not.toBeInTheDocument();
    // The original conflicting UUID is surfaced so the operator
    // can correlate with the row in the table.
    expect(specificMessage.textContent).toContain(editingUuid);
    __mockTipos = SAMPLE_TIPOS.slice(0, 2);
  });

  it('CP16: a successful EDIT invalidates the by-key SWR cache so the "Ver histórico" panel picks up the new version without F5', async () => {
    // Operator-reported bug: after editing a cupo and reopening the
    // "Ver histórico" panel on the same (sucursal, tipo_vehiculo) cell,
    // the panel kept showing the pre-edit chain — the operator had to
    // F5 to see the new version. Root cause: the page only invalidated
    // the list SWR cache (``useCantidadList::refresh`` — branch-scoped
    // since the 2026-10-13 fix, key ``['cupos-list', sucursal]``) and
    // not the by-key cache used by ``useCantidadByKey``; the SWR
    // ``dedupingInterval: 5min`` returned the stale chain.
    //
    // The fix (``Cupos.tsx::invalidateByKey``) explicitly calls
    // ``useSWRConfig().mutate(byKeyKey)`` after every successful write.
    // The regression test asserts the by-key mock is called TWICE:
    // once when the panel first opens, and once after the edit
    // invalidates the cache — without the fix, only the first call
    // would happen.
    const editingUuid = '1a231f57-cb96-4284-b4b0-f3e7c594f632';
    const tipoUuid = '00000000-0000-0000-0000-000000000003'; // bicicleta
    const editingRow = {
      ...SAMPLE_CUPO,
      uuid: editingUuid,
      uuid_sucursal: SUCURSAL_1,
      uuid_tipo_vehiculo: tipoUuid,
      cantidad: 5,
      vigente_desde: '2026-10-09T22:35:00',
    };
    const newRow = { ...editingRow, uuid: '2b342f68-dea7-5395-c5c1-0408d6a5f743', cantidad: 7 };
    // First call: pre-edit chain. Second call: post-edit chain (with the new version).
    mockedListByKey
      .mockResolvedValueOnce([editingRow])
      .mockResolvedValueOnce([newRow, editingRow]);
    mockedListCupos
      .mockResolvedValueOnce([editingRow])
      .mockResolvedValueOnce([newRow]);
    mockedUpdateCupo.mockResolvedValue(newRow);
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUCURSAL_1);
    const user = userEvent.setup();
    render(<Cupos />, { wrapper: fullWrapper });
    await waitFor(() =>
      expect(screen.getByTestId(`cupo-row-${editingUuid}`)).toBeInTheDocument(),
    );
    // 1) Open "Ver histórico" on the row → first by-key call.
    await user.click(screen.getByTestId(`cupo-history-${editingUuid}`));
    await waitFor(() =>
      expect(mockedListByKey).toHaveBeenCalledTimes(1),
    );
    // 2) Edit and submit → invalidates the by-key cache, second call.
    await user.click(screen.getByTestId(`cupo-edit-${editingUuid}`));
    await user.click(screen.getByTestId('cupo-submit'));
    await waitFor(() =>
      expect(mockedListByKey).toHaveBeenCalledTimes(2),
    );
    // The second call's response (the new chain) is what the panel
    // shows on the next render — verify the mock is wired to return it.
    await expect(mockedListByKey.mock.results[1]?.value).resolves.toEqual([
      newRow,
      editingRow,
    ]);
  });

  it('CP17: a row with vigente_desde in the future (close+insert boundary) shows a "Programado" badge', async () => {
    // Operator-reported bug 2026-10-11: edit a cupo, the new row
    // has ``vigente_desde = now + 1min``, the list filter excluded
    // it during the "in transition" gap. After the list query fix
    // (latest per cell), the row is always shown; the badge
    // surfaces the scheduled state so the operator knows the
    // change is not vigente yet.
    //
    // We anchor the row's ``vigente_desde`` 1 hour in the future of
    // ``new Date()`` at test time so the assertion is robust against
    // clock drift between the CI host and the test run. ``useFakeTimers``
    // was tried first and broke the SWR revalidation in unrelated
    // tests; the relative-time approach is the simpler fix.
    const futureIso = new Date(Date.now() + 60 * 60 * 1000).toISOString();
    const scheduledRow = {
      ...SAMPLE_CUPO,
      uuid_sucursal: SUCURSAL_1,
      uuid_tipo_vehiculo: '00000000-0000-0000-0000-000000000001', // carro
      cantidad: 12,
      vigente_desde: futureIso,
      vigente_hasta: null,
      estado: 'activo',
    };
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUCURSAL_1);
    mockedListCupos.mockResolvedValue([scheduledRow]);
    render(<Cupos />, { wrapper: fullWrapper });
    await waitFor(() => {
      expect(screen.getByTestId(`cupo-row-${scheduledRow.uuid}`)).toBeInTheDocument();
    });
    // The "Programado" badge is rendered.
    const badge = screen.getByTestId(`cupo-scheduled-${scheduledRow.uuid}`);
    expect(badge).toBeInTheDocument();
    expect(badge.textContent).toMatch(/programado/i);
  });

  it('CP18: a row with vigente_desde in the past does NOT show a "Programado" badge', async () => {
    const pastIso = new Date(Date.now() - 60 * 60 * 1000).toISOString();
    const vigenteRow = {
      ...SAMPLE_CUPO,
      uuid_sucursal: SUCURSAL_1,
      uuid_tipo_vehiculo: '00000000-0000-0000-0000-000000000001',
      cantidad: 12,
      vigente_desde: pastIso,
      vigente_hasta: null,
      estado: 'activo',
    };
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUCURSAL_1);
    mockedListCupos.mockResolvedValue([vigenteRow]);
    render(<Cupos />, { wrapper: fullWrapper });
    await waitFor(() => {
      expect(screen.getByTestId(`cupo-row-${vigenteRow.uuid}`)).toBeInTheDocument();
    });
    // No "Programado" badge — the row is vigente.
    expect(
      screen.queryByTestId(`cupo-scheduled-${vigenteRow.uuid}`),
    ).not.toBeInTheDocument();
  });

  it('CP19 (HU-X.8 follow-up): the header hosts a branch combobox that writes through to the global SucursalContext', async () => {
    // Operator flow: admin lands on /cupos from /dashboard with
    // SUCURSAL_1 already active. The combobox reflects the selection
    // and the table is filtered to that branch.
    const SUCURSAL_2 = '22222222-2222-2222-2222-222222222222';
    mockedListSucursales.mockResolvedValue([
      { uuid: SUCURSAL_1, nombre: 'Sucursal Centro', prefijo_nombre: 'CEN' },
      { uuid: SUCURSAL_2, nombre: 'Sucursal Norte', prefijo_nombre: 'NOR' },
    ]);
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUCURSAL_1);
    mockedListCupos.mockResolvedValue([
      { ...SAMPLE_CUPO, uuid_sucursal: SUCURSAL_1, cantidad: 50 },
      {
        ...SAMPLE_CUPO,
        uuid: '99999999-9999-9999-9999-999999999999',
        uuid_sucursal: SUCURSAL_2,
        cantidad: 99,
      },
    ]);
    render(<Cupos />, { wrapper: fullWrapper });
    await waitFor(() => {
      expect(screen.getByTestId('cupos-branch-combobox')).toBeInTheDocument();
    });
    // The legacy "Actual: <nombre>" hint paragraph under the combobox
    // was removed by HU-fix-usuarios-alignment (the same data-testid
    // was used here). The active branch is now shown via the input's
    // own value; the subtitle names the branch directly.
    await waitFor(() => {
      expect(screen.getByTestId('cupos-active-branch-name')).toBeInTheDocument();
    });
    // The subtitle names the active branch.
    expect(screen.getByTestId('cupos-active-branch-name').textContent).toMatch(
      /Sucursal Centro/,
    );
    // The table is filtered to the active branch.
    expect(
      screen.getByTestId('cupo-row-aaaaaaaa-1111-1111-1111-111111111111'),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId('cupo-row-99999999-9999-9999-9999-999999999999'),
    ).not.toBeInTheDocument();
  });

  it('CP20 (HU-X.8 follow-up): switching branches mid-edit closes the create/edit modal automatically', async () => {
    // Operator-reported edge case: open the create modal, switch
    // branches via the combobox, the modal MUST close — the BE
    // rejects any `uuid_sucursal` swap on a cupo
    // (HTTP 409 `cantidad_sucursal_inmutable`), so a stale modal
    // would surface an opaque error on submit.
    const SUCURSAL_2 = '22222222-2222-2222-2222-222222222222';
    mockedListSucursales.mockResolvedValue([
      { uuid: SUCURSAL_1, nombre: 'Sucursal Centro', prefijo_nombre: 'CEN' },
      { uuid: SUCURSAL_2, nombre: 'Sucursal Norte', prefijo_nombre: 'NOR' },
    ]);
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUCURSAL_1);
    mockedListCupos.mockResolvedValue([]);
    const user = userEvent.setup();
    render(<Cupos />, { wrapper: fullWrapper });
    await waitFor(() => screen.getByTestId('cupo-empty'));
    // Open the create modal.
    await user.click(screen.getByTestId('cupo-new'));
    expect(screen.getByTestId('cupo-form-modal')).toBeInTheDocument();
    // Switch the active branch from the topbar (the inline combobox
    // is in the header; the page-level test exercises the same
    // `useSucursal().selected` subscription via the same effect).
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUCURSAL_2);
    // Re-render the page by toggling a noop state through the
    // existing `localStorage.setItem` triggers a `storage` event
    // on the window — but `SucursalProvider` reads the initial value
    // on mount and does not subscribe to `storage` events. The
    // realistic path is: user opens the combobox, picks a branch,
    // the combobox calls `setSelected`, which re-renders the page.
    // Easiest cross-test seam: dispatch the React update via
    // `act(() => window.localStorage.setItem(...))` does NOT trigger
    // a re-render. Instead, exercise the same hook path the real UI
    // uses: click the combobox, then the new-branch option.
    const input = screen.getByTestId('cupos-branch-combobox');
    await user.click(input);
    const newOption = await screen.findByTestId(
      `cupos-branch-combobox-option-${SUCURSAL_2}`,
    );
    await user.click(newOption);
    // The modal must close on branch change.
    await waitFor(() => {
      expect(screen.queryByTestId('cupo-form-modal')).not.toBeInTheDocument();
    });
    // And the global context now points at SUCURSAL_2.
    expect(window.localStorage.getItem('parkos.lastSelectedSucursal')).toBe(
      SUCURSAL_2,
    );
  });

  it('CP21: switching the active branch re-fetches the list and shows rows for the new branch (no F5)', async () => {
    // Operator-reported bug (2026-10-13): on /dashboard, the
    // "CUPOS VIGENTES" quick-link showed 0 (or the wrong number)
    // for the freshly-picked branch, and only updated after a hard
    // refresh. Same symptom inside /cupos: changing the inline
    // branch picker left the list showing rows for the previous
    // branch (or empty if the BE filtered them out), forcing an F5.
    //
    // Root cause: ``useCantidadList`` used a static SWR key
    // ``'cupos-list'`` but the BE filters the list by
    // ``X-Sucursal-Context`` (HU-F15.1 BR4 + tenant listener). The
    // static key meant SWR served the previous branch's data within
    // the 5-minute deduping interval.
    //
    // Fix: branch-scoped SWR key ``['cupos-list', sucursal]`` so
    // each branch has its own cache entry and changing the active
    // branch triggers a fresh fetch.
    //
    // Regression assertions:
    //   1. The list mock is called TWICE (once per branch selection).
    //   2. The rendered table for SUCURSAL_1 only shows the SUCURSAL_1
    //      rows.
    //   3. After switching to SUCURSAL_2, the list mock's second
    //      response (SUCURSAL_2 rows) is what renders — not a stale
    //      SUCURSAL_1 row.
    const SUCURSAL_2 = '22222222-2222-2222-2222-222222222222';
    const SUCURSAL_1_ROW = {
      ...SAMPLE_CUPO,
      uuid: 'aaaaaaaa-1111-1111-1111-111111111111',
      uuid_sucursal: SUCURSAL_1,
      cantidad: 10,
    };
    const SUCURSAL_2_ROW_A = {
      ...SAMPLE_CUPO,
      uuid: 'ccccccc1-2222-2222-2222-222222222222',
      uuid_sucursal: SUCURSAL_2,
      cantidad: 20,
    };
    const SUCURSAL_2_ROW_B = {
      ...SAMPLE_CUPO,
      uuid: 'ccccccc2-2222-2222-2222-222222222222',
      uuid_sucursal: SUCURSAL_2,
      cantidad: 30,
    };
    mockedListSucursales.mockResolvedValue([
      { uuid: SUCURSAL_1, nombre: 'Sucursal Centro', prefijo_nombre: 'CEN' },
      { uuid: SUCURSAL_2, nombre: 'Sucursal Norte', prefijo_nombre: 'NOR' },
    ]);
    // First list call (SUCURSAL_1 mount): one row.
    // Second list call (after switching to SUCURSAL_2): two rows.
    mockedListCupos
      .mockResolvedValueOnce([SUCURSAL_1_ROW])
      .mockResolvedValueOnce([SUCURSAL_2_ROW_A, SUCURSAL_2_ROW_B]);
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUCURSAL_1);
    const user = userEvent.setup();
    render(<Cupos />, { wrapper: fullWrapper });
    // (1) Initial mount fetched for SUCURSAL_1.
    await waitFor(() =>
      expect(
        screen.getByTestId('cupo-row-aaaaaaaa-1111-1111-1111-111111111111'),
      ).toBeInTheDocument(),
    );
    expect(mockedListCupos).toHaveBeenCalledTimes(1);
    // (2) Switch the active branch via the inline combobox.
    const input = screen.getByTestId('cupos-branch-combobox');
    await user.click(input);
    const newOption = await screen.findByTestId(
      `cupos-branch-combobox-option-${SUCURSAL_2}`,
    );
    await user.click(newOption);
    // (3) The branch-scoped SWR key change triggers a refetch — the
    // mock must be called a second time (NOT served from the stale
    // SUCURSAL_1 cache).
    await waitFor(() => expect(mockedListCupos).toHaveBeenCalledTimes(2));
    // (4) The list shows the SUCURSAL_2 rows, NOT the SUCURSAL_1 row.
    await waitFor(() =>
      expect(
        screen.getByTestId('cupo-row-ccccccc1-2222-2222-2222-222222222222'),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByTestId('cupo-row-ccccccc2-2222-2222-2222-222222222222'),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId('cupo-row-aaaaaaaa-1111-1111-1111-111111111111'),
    ).not.toBeInTheDocument();
  });
});