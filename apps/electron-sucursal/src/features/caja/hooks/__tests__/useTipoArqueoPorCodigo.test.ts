/**
 * D4 — la clave SWR debe incluir `codigo`: de lo contrario todos los códigos
 * comparten una entrada de caché y `cerrar turno` enviaba el uuid de cierre_dia.
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

const { useTipoArqueoPorCodigo } = await import('../useTipoArqueoPorCodigo');
const { parkosFetch } = await import('@parkos/ui-kit/fetch');
const mockedFetch = vi.mocked(parkosFetch);

const UUID_DIA = '11111111-1111-4111-8111-111111111111';
const UUID_TURNO = '22222222-2222-4222-8222-222222222222';
const catalogo = {
  items: [
    { uuid: UUID_DIA, codigo: 'cierre_dia', nombre: 'Cierre dia', descripcion: null },
    { uuid: UUID_TURNO, codigo: 'cierre_turno', nombre: 'Cierre turno', descripcion: null },
  ],
};

describe('D4 — useTipoArqueoPorCodigo no comparte caché entre códigos', () => {
  beforeEach(() => mockedFetch.mockReset());

  it('resuelve el uuid propio de cada código aunque se monten consecutivamente', async () => {
    mockedFetch.mockResolvedValue(catalogo as never);
    const dia = renderHook(() => useTipoArqueoPorCodigo('cierre_dia'));
    await waitFor(() => expect(dia.result.current.uuid).toBe(UUID_DIA));

    const turno = renderHook(() => useTipoArqueoPorCodigo('cierre_turno'));
    await waitFor(() => expect(turno.result.current.uuid).toBeDefined());
    expect(turno.result.current.uuid).toBe(UUID_TURNO);
    expect(turno.result.current.data?.codigo).toBe('cierre_turno');
  });
});
