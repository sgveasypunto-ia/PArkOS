/**
 * Unit tests for `sesionActivaApi` (F3.3 — T1).
 *
 * Cobertura U5..U8 (cross-ref tasks.md §2):
 *   U5: getSesionActiva() 200 → SesionRead parseado.
 *   U6: getSesionActiva() 404 → null (operador sin turno es estado válido).
 *   U7: abrirSesion() 409 → throws SesionAlreadyActiveError (status=409,
 *        code='sesion_already_active').
 *   U8: cerrarSesion() 200 → SesionRead con timestamp_cierre poblado.
 *
 * Mocking strategy: vi.mock('@parkos/ui-kit/fetch') — mismo pattern F3.1
 * `loginApi.test.ts:14-22` (verificado). parkosFetch stub permite inyectar
 * status + body + url sin red.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';

import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import {
  getSesionActiva,
  abrirSesion,
  cerrarSesion,
  SesionAlreadyActiveError,
  SesionAlreadyClosedError,
} from './sesionActivaApi';

const parkosFetchMock = vi.fn();

vi.mock('@parkos/ui-kit/fetch', () => ({
  ParkosHttpError: class extends Error {
    public readonly status: number;
    public readonly body: string;
    public readonly url: string;
    constructor(status: number, body: string, url: string) {
      super(`parkosFetch ${status} ${url}: ${body.slice(0, 200)}`);
      this.name = 'ParkosHttpError';
      this.status = status;
      this.body = body;
      this.url = url;
    }
  },
  parkosFetch: (...args: unknown[]) => parkosFetchMock(...args),
}));

afterEach(() => {
  vi.clearAllMocks();
});

const baseSesion = {
  uuid: 'sess-uuid-1',
  uuid_sucursal: 'suc-uuid-1',
  uuid_usuario: 'usr-uuid-1',
  valor_inicial_efectivo: 50000,
  valor_inicial_datafono: 0,
  timestamp_apertura: '2026-09-15T08:00:00Z',
  timestamp_cierre: null,
  observaciones: 'Apertura',
};

describe('getSesionActiva', () => {
  it('U5: 200 OK retorna SesionRead parseado', async () => {
    parkosFetchMock.mockResolvedValueOnce(baseSesion);
    const result = await getSesionActiva();
    expect(result).toEqual(baseSesion);
    expect(parkosFetchMock).toHaveBeenCalledWith('/api/v1/caja-sesion/sesion/me');
  });

  it('U6: 404 Not Found → null, NO lanza (operador sin turno es estado válido)', async () => {
    parkosFetchMock.mockRejectedValueOnce(
      new ParkosHttpError(404, '{"error":"sesion_no_active"}', '/api/v1/caja-sesion/sesion/me'),
    );
    const result = await getSesionActiva();
    expect(result).toBeNull();
  });

  it('U6b: 500 → propaga ParkosHttpError sin swallow', async () => {
    parkosFetchMock.mockRejectedValueOnce(
      new ParkosHttpError(500, '{"error":"server_error"}', '/api/v1/caja-sesion/sesion/me'),
    );
    await expect(getSesionActiva()).rejects.toBeInstanceOf(ParkosHttpError);
  });
});

describe('abrirSesion', () => {
  it('U7: 409 sesion_already_active → throws SesionAlreadyActiveError', async () => {
    parkosFetchMock.mockRejectedValue(
      new ParkosHttpError(409, '{"error":"sesion_already_active"}', '/api/v1/caja-sesion/sesiones'),
    );
    await expect(
      abrirSesion({
        uuid_sucursal: 'suc-uuid-1',
        uuid_usuario: 'usr-uuid-1',
        valor_inicial_efectivo: 50000,
        valor_inicial_datafono: 0,
      }),
    ).rejects.toBeInstanceOf(SesionAlreadyActiveError);
    await expect(
      abrirSesion({
        uuid_sucursal: 'suc-uuid-1',
        uuid_usuario: 'usr-uuid-1',
        valor_inicial_efectivo: 0,
        valor_inicial_datafono: 0,
      }),
    ).rejects.toMatchObject({ status: 409, code: 'sesion_already_active' });
  });

  it('U7b: 200 OK retorna SesionRead', async () => {
    parkosFetchMock.mockResolvedValueOnce(baseSesion);
    const result = await abrirSesion({
      uuid_sucursal: 'suc-uuid-1',
      uuid_usuario: 'usr-uuid-1',
      valor_inicial_efectivo: 50000,
      valor_inicial_datafono: 0,
    });
    expect(result).toEqual(baseSesion);
    expect(parkosFetchMock).toHaveBeenCalledWith(
      '/api/v1/caja-sesion/sesiones',
      expect.objectContaining({ method: 'POST' }),
    );
  });
});

describe('cerrarSesion', () => {
  it('U8: 200 OK retorna SesionRead con timestamp_cierre poblado', async () => {
    const sesionCerrada = {
      ...baseSesion,
      timestamp_cierre: '2026-09-15T18:00:00Z',
    };
    parkosFetchMock.mockResolvedValueOnce(sesionCerrada);
    const result = await cerrarSesion('sess-uuid-1', {
      valor_final_efectivo: 75000,
      valor_final_datafono: 25000,
    });
    expect(result).toEqual(sesionCerrada);
    expect(result.timestamp_cierre).toBe('2026-09-15T18:00:00Z');
    expect(parkosFetchMock).toHaveBeenCalledWith(
      '/api/v1/caja-sesion/sesion/sess-uuid-1/cerrar',
      expect.objectContaining({ method: 'PUT' }),
    );
  });

  it('U8b: 404 sesion_not_found → throws SesionAlreadyClosedError', async () => {
    parkosFetchMock.mockRejectedValueOnce(
      new ParkosHttpError(
        404,
        '{"error":"sesion_not_found"}',
        '/api/v1/caja-sesion/sesion/sess-uuid-1/cerrar',
      ),
    );
    await expect(
      cerrarSesion('sess-uuid-1', {
        valor_final_efectivo: 0,
        valor_final_datafono: 0,
      }),
    ).rejects.toBeInstanceOf(SesionAlreadyClosedError);
  });
});