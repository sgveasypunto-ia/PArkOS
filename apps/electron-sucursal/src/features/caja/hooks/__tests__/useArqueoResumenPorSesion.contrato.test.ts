/**
 * D3 — contrato real de `GET /caja/arqueo/resumen` (REQ-OPS-192): el backend
 * ya NO devuelve los campos datafono y serializa los Decimal como string.
 * El cliente no debe producir NaN ni exponer un ZodError crudo.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

vi.mock('@parkos/ui-kit/fetch', () => ({
  parkosFetch: vi.fn(),
  ParkosHttpError: class ParkosHttpError extends Error {
    readonly status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
      this.name = 'ParkosHttpError';
    }
  },
}));

const FAKE_AUTH_STATE = { accessToken: 'tok' };
vi.mock('@parkos/ui-kit/store', () => ({
  useAuthStore: Object.assign(
    (selector: (s: typeof FAKE_AUTH_STATE) => unknown) => selector(FAKE_AUTH_STATE),
    { getState: () => ({ ...FAKE_AUTH_STATE, clear: vi.fn() }) },
  ),
}));

const { useArqueoResumenPorSesion } = await import('../useArqueoResumenPorSesion');
const { parkosFetch } = await import('@parkos/ui-kit/fetch');
const mockedFetch = vi.mocked(parkosFetch);

const item = {
  uuid_sesion: '22222222-3333-4444-8555-666666666666',
  uuid_usuario: 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee',
  timestamp_apertura: '2026-10-06T13:00:00',
  timestamp_cierre: '2026-10-06T23:00:00',
  estado: 'cerrado',
  valor_efectivo_esperado: '50000.0000',
  valor_efectivo_reportado: '50000.0000',
  uuid_arqueo: 'cccccccc-dddd-4eee-8fff-111111111111',
};

describe('D3 — useArqueoResumenPorSesion contra el contrato sin datafono', () => {
  beforeEach(() => mockedFetch.mockReset());

  it('acepta items sin campos datafono y coacciona los Decimal string a number', async () => {
    mockedFetch.mockResolvedValueOnce({
      fecha: '2026-10-06',
      uuid_sucursal: 'd3d3d3d3-2222-4333-8444-000000000001',
      sesiones: [item],
      cierre_dia: null,
    } as never);
    const { result } = renderHook(() =>
      useArqueoResumenPorSesion('d3d3d3d3-2222-4333-8444-000000000001', '2026-10-06'),
    );
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.error).toBeUndefined();
    expect(result.current.data?.sesiones[0]?.valor_efectivo_esperado).toBe(50000);
    expect(result.current.data?.sesiones[0]?.valor_efectivo_reportado).toBe(50000);
  });

  it('tolera campos datafono heredados sin fallar', async () => {
    mockedFetch.mockResolvedValueOnce({
      fecha: '2026-10-06',
      uuid_sucursal: 'd3d3d3d3-2222-4333-8444-000000000002',
      sesiones: [{ ...item, valor_datafono_esperado: '0', valor_datafono_reportado: '0' }],
      cierre_dia: null,
    } as never);
    const { result } = renderHook(() =>
      useArqueoResumenPorSesion('d3d3d3d3-2222-4333-8444-000000000002', '2026-10-06'),
    );
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.error).toBeUndefined();
  });

  it('un payload fuera de contrato produce un error amigable, nunca un ZodError crudo', async () => {
    mockedFetch.mockResolvedValue({ fecha: '2026-10-06', basura: true } as never);
    const { result } = renderHook(() =>
      useArqueoResumenPorSesion('d3d3d3d3-2222-4333-8444-000000000003', '2026-10-06'),
    );
    await waitFor(() => expect(result.current.error).toBeDefined(), { timeout: 8000 });
    const err = result.current.error as Error;
    expect(err.name).not.toBe('ZodError');
    expect(err.message).not.toMatch(/"code"|invalid_type|\[\s*\{/);
    expect(err.message).toMatch(/resumen/i);
  }, 12000);
});
