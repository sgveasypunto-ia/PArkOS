/**
 * `SucursalGeneralForm.test.tsx` — tests for the "General" tab of
 * `SucursalDetalle` (HU-F15.1).
 *
 * Covers the live defect found QA-testing this tab (2026-10-02): a
 * successful save regenerates `uuid` (bi-temporal close+insert, same
 * mechanism as the admin table's edit flow in `SeleccionarSucursal`),
 * so `onUpdated` MUST receive the fresh `Sucursal` row -- a caller that
 * only re-fetches the OLD route uuid 404s ("no existe o ya no está
 * vigente") right after a successful save.
 *
 *   T1: required-field validation (empty "Nombre") blocks the submit
 *       client-side -- no `updateSucursal` call, error message shown.
 *   T2: a successful save calls `onUpdated` with the updated `Sucursal`
 *       (the NEW uuid), not with no arguments.
 *   T3: confirming the disable dialog calls `disableSucursal` + the
 *       `onDeshabilitada` callback.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../../sucursales/api/sucursalesApi', () => ({
  updateSucursal: vi.fn(),
  disableSucursal: vi.fn(),
  SucursalDeshabilitarBloqueadoError: class SucursalDeshabilitarBloqueadoError extends Error {},
}));

vi.mock('@/features/empresa/hooks/useEmpresa', () => ({
  useEmpresa: () => ({
    empresa: { uuid: 'eeeeeeee-0000-0000-0000-000000000000' },
    isLoading: false,
    error: undefined,
    refresh: vi.fn(),
  }),
}));

vi.mock('@/features/tipo-sucursal/hooks/useTipoSucursal', () => ({
  useTipoSucursal: () => ({
    tipos: [],
    isLoading: false,
    error: undefined,
    refresh: vi.fn(),
    isFromFallback: false,
  }),
}));

import {
  disableSucursal,
  updateSucursal,
} from '../../sucursales/api/sucursalesApi';
import { SucursalGeneralForm } from './SucursalGeneralForm';
import type { Sucursal } from '../../sucursales/api/sucursalSchema';

const mockedUpdateSucursal = updateSucursal as ReturnType<typeof vi.fn>;
const mockedDisableSucursal = disableSucursal as ReturnType<typeof vi.fn>;

const OLD_UUID = 'aaaaaaaa-1111-1111-1111-111111111111';
const NEW_UUID = 'bbbbbbbb-2222-2222-2222-222222222222';

const SUCURSAL: Sucursal = {
  uuid: OLD_UUID,
  nombre: 'Sucursal QA',
  direccion: 'Cra 1',
  telefono: '+573001234567',
  prefijo_nombre: 'QA-001',
  ciudad: 'Bogota',
  horario: '24/7',
  uuid_tipo_sucursal: null,
  uuid_empresa: null,
  vigente_desde: '2026-01-01T00:00:00',
  vigente_hasta: null,
  estado: 'activo',
  created_at: '2026-01-01T00:00:00',
  created_by: null,
  sync_status: 'sincronizado',
};

beforeEach(() => {
  mockedUpdateSucursal.mockReset();
  mockedDisableSucursal.mockReset();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('SucursalGeneralForm', () => {
  it('T1: nombre vacío bloquea el submit sin llamar a updateSucursal', async () => {
    const user = userEvent.setup();
    const onUpdated = vi.fn().mockResolvedValue(undefined);
    render(
      <SucursalGeneralForm
        sucursal={SUCURSAL}
        onUpdated={onUpdated}
        onDeshabilitada={vi.fn()}
      />,
    );

    await user.clear(screen.getByTestId('sucursal-general-nombre'));
    await user.click(screen.getByTestId('sucursal-general-submit'));

    expect(await screen.findByText('El nombre es obligatorio')).toBeInTheDocument();
    expect(mockedUpdateSucursal).not.toHaveBeenCalled();
    expect(onUpdated).not.toHaveBeenCalled();
  });

  it('T2: guardar con éxito llama a onUpdated con la sucursal actualizada (uuid nuevo)', async () => {
    const user = userEvent.setup();
    const updatedSucursal: Sucursal = { ...SUCURSAL, uuid: NEW_UUID, ciudad: 'Medellin' };
    mockedUpdateSucursal.mockResolvedValue(updatedSucursal);
    const onUpdated = vi.fn().mockResolvedValue(undefined);

    render(
      <SucursalGeneralForm
        sucursal={SUCURSAL}
        onUpdated={onUpdated}
        onDeshabilitada={vi.fn()}
      />,
    );

    await user.clear(screen.getByTestId('sucursal-general-ciudad'));
    await user.type(screen.getByTestId('sucursal-general-ciudad'), 'Medellin');
    await user.click(screen.getByTestId('sucursal-general-submit'));

    await waitFor(() => expect(mockedUpdateSucursal).toHaveBeenCalledTimes(1));
    expect(mockedUpdateSucursal).toHaveBeenCalledWith(OLD_UUID, expect.objectContaining({ ciudad: 'Medellin' }));
    await waitFor(() => expect(onUpdated).toHaveBeenCalledWith(updatedSucursal));
    // The regression this test pins: the callback must carry the NEW
    // uuid, never just be invoked with no arguments.
    expect(onUpdated.mock.calls[0]?.[0]?.uuid).toBe(NEW_UUID);
  });

  it('T3: confirmar el diálogo de deshabilitar llama a disableSucursal + onDeshabilitada', async () => {
    const user = userEvent.setup();
    mockedDisableSucursal.mockResolvedValue(undefined);
    const onDeshabilitada = vi.fn().mockResolvedValue(undefined);

    render(
      <SucursalGeneralForm
        sucursal={SUCURSAL}
        onUpdated={vi.fn()}
        onDeshabilitada={onDeshabilitada}
      />,
    );

    await user.click(screen.getByTestId('sucursal-general-deshabilitar-btn'));
    await user.click(screen.getByTestId('sucursal-deshabilitar-confirmar'));

    await waitFor(() => expect(mockedDisableSucursal).toHaveBeenCalledWith(OLD_UUID));
    await waitFor(() => expect(onDeshabilitada).toHaveBeenCalledTimes(1));
  });
});
