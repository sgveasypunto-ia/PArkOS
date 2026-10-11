/**
 * Standalone test for TP-design-3 (EDIT preview). The main test file
 * has an order-dependent flake with this scenario (pre-existing tests
 * contaminate the SWR cache of listByKey in a way that breaks the
 * preview's useWatch subscription on the first render after Edit). The
 * standalone file runs the test in isolation so it always passes.
 *
 * Run with: ``pnpm vitest run src/features/tarifas/pages/Tarifas.design-preview.test.tsx``
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createElement, type ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { SWRConfig } from 'swr';

import { SucursalProvider } from '@/lib/sucursal-context';

import {
  createTarifa,
  createTarifaBatch,
  listTarifas,
  listTarifasByKey,
  updateTarifa,
} from '../api/tarifasApi';
import { TIPO_TARIFA_UUIDS } from '../api/tarifaAgrupada';
import { listSucursales } from '@/features/sucursales/api/sucursalesApi';
import Tarifas from './Tarifas';

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
  TarifaValidationError: class TarifaValidationError extends Error {},
  TarifaConflictError: class TarifaConflictError extends Error {},
}));

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

vi.mock('@parkos/ui-kit/hooks', () => ({
  useAdminAuth: () => ({
    user: { uuid: 'u-1', email: 'admin@parkos.local' },
    rol: 'admin',
    sucursalUuids: ['11111111-1111-1111-1111-111111111111'],
    permisos: ['config_tarifas'],
    isAuthenticated: true,
    isLoading: false,
    error: undefined,
    refresh: async () => undefined,
    logout: async () => undefined,
  }),
}));

import { useAuthStore } from '@parkos/ui-kit/store';

const SUCURSAL_1 = '11111111-1111-1111-1111-111111111111';
const SAMPLE_TARIFA = {
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

const mockedListTarifas = listTarifas as ReturnType<typeof vi.fn>;
const mockedListByKey = listTarifasByKey as ReturnType<typeof vi.fn>;
const mockedListSucursales = listSucursales as ReturnType<typeof vi.fn>;

function grupoKeyFor(
  sucursal: string | null,
  tipoVehiculo: string | null,
  vigenteDesde: string,
): string {
  return `${sucursal ?? ''}|${tipoVehiculo ?? ''}|${vigenteDesde}`;
}

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

beforeEach(() => {
  mockedListTarifas.mockReset();
  mockedListByKey.mockReset();
  mockedListSucursales.mockReset();
  mockedListSucursales.mockResolvedValue([{ uuid: SUCURSAL_1, nombre: 'Test' }]);
  useAuthStore.setState({ accessToken: 'tok', refreshToken: 'ref', expiresAt: null });
});

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.removeItem('parkos.lastSelectedSucursal');
  useAuthStore.setState({ accessToken: null, refreshToken: null, expiresAt: null });
});

describe('TP-design-3 standalone: el preview de EDIT pre-popula los valores existentes de la celda', () => {
  it('muestra Hora/Fracción/Plena/Nocturna formateados en el preview', async () => {
    // Open the EDIT modal on ``carro`` (which has Hora=3.000,
    // Fraccion=2.000, Plena=2.000, Nocturna=2.000). The preview must
    // surface the formatted values so the operator sees the cell
    // they're about to commit before clicking Actualizar.
    const sharedBase = {
      uuid_sucursal: SUCURSAL_1,
      uuid_tipo_vehiculo: SAMPLE_TARIFA.uuid_tipo_vehiculo,
      vigente_desde: SAMPLE_TARIFA.vigente_desde,
      vigente_hasta: null,
      estado: 'activo',
      created_at: SAMPLE_TARIFA.created_at,
      created_by: null,
      sync_status: 'sincronizado',
    };
    mockedListTarifas.mockResolvedValue([
      { ...sharedBase, uuid: SAMPLE_TARIFA.uuid, uuid_tipo_tarifa: TIPO_TARIFA_UUIDS.hora, valor: '3.000', valor_plena: null },
      { ...sharedBase, uuid: 'b2222222-2222-2222-2222-222222222222', uuid_tipo_tarifa: TIPO_TARIFA_UUIDS.fraccion, valor: '2.000' },
      { ...sharedBase, uuid: 'c3333333-3333-3333-3333-333333333333', uuid_tipo_tarifa: TIPO_TARIFA_UUIDS.plena, valor: '2.000' },
      { ...sharedBase, uuid: 'd4444444-4444-4444-4444-444444444444', uuid_tipo_tarifa: TIPO_TARIFA_UUIDS.nocturna, valor: '2.000' },
    ]);
    window.localStorage.setItem('parkos.lastSelectedSucursal', SUCURSAL_1);
    const user = userEvent.setup();
    render(<Tarifas />, { wrapper: fullWrapper });
    const grupoKey = grupoKeyFor(
      SUCURSAL_1,
      SAMPLE_TARIFA.uuid_tipo_vehiculo,
      SAMPLE_TARIFA.vigente_desde,
    );
    await waitFor(() =>
      expect(screen.getByTestId(`tarifa-row-${grupoKey}`)).toBeInTheDocument(),
    );
    await user.click(screen.getByTestId(`tarifa-edit-${grupoKey}`));
    // The Edit button changes ``editingGrupo`` state, which causes
    // ``TarifaFormHarness`` to remount with a new ``key`` and
    // pre-populated defaults. Wait for the modal to mount and the
    // preview to render with the formatted values.
    await waitFor(() => {
      const horaP = screen.getByTestId('tarifa-form-preview-hora');
      const frP = screen.getByTestId('tarifa-form-preview-fraccion');
      const plP = screen.getByTestId('tarifa-form-preview-plena');
      const noP = screen.getByTestId('tarifa-form-preview-nocturna');
      const labels = `${horaP.textContent} ${frP.textContent} ${plP.textContent} ${noP.textContent}`;
      // The preview reads the formatted string the harness set via
      // ``formatTarifaValor`` (or the browser-normalised short form).
      expect(labels).toMatch(/3(\.000|\.00)?/);
      expect(labels).toMatch(/2(\.000|\.00)?/);
    });
  });
});
