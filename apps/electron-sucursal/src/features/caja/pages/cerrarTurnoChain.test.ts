/**
 * `cerrarTurnoChain.test.ts` — dedicated coverage for the 8-case
 * precedence chain (HU-F10.2), previously a documented gap
 * (`CerrarTurno.test.tsx` only smoke-tested the container).
 *
 * Bugfix (2026-10-01): "en logs no se ve nada" — every error branch of
 * `runCerrarTurnoChain` swallowed `err`/`result` into the result
 * envelope with zero trace. This file locks in that every non-success
 * branch now calls `console.error('[cerrarTurnoChain] ...', ...)`
 * before returning, so a future regression that silences a branch
 * again fails a test instead of shipping unnoticed.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import { runCerrarTurnoChain } from './cerrarTurnoChain';
import type { SesionRead } from '../api/sesionActivaApi';

const SESION: SesionRead = {
  uuid: 'sess-uuid-1',
  uuid_sucursal: 'suc-uuid-1',
  uuid_usuario: 'usr-uuid-1',
  valor_inicial_efectivo: 100_000,
  valor_inicial_datafono: 0,
  timestamp_apertura: '2026-09-21T08:00:00Z',
  timestamp_cierre: null,
};

const BASE_VALUES = {
  valor_efectivo_reportado: 100_000,
  valor_datafono_reportado: 0,
  justificacion: '',
  observaciones_cierre: '',
};

const baseArgs = () => ({
  sesion: SESION,
  uuidTipoArqueo: 'tipo-arqueo-uuid-1',
  bridge: null,
  values: BASE_VALUES,
});

let consoleErrorSpy: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(() => {
  consoleErrorSpy.mockRestore();
});

describe('runCerrarTurnoChain — logging (Cambio 4)', () => {
  it('red_arqueo (network TypeError) → console.error + kind red_arqueo', async () => {
    const submitArqueo = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'));
    const cerrarSesion = vi.fn();

    const result = await runCerrarTurnoChain({
      ...baseArgs(),
      submitArqueo,
      cerrarSesion,
    });

    expect(result).toEqual({ kind: 'red_arqueo' });
    expect(consoleErrorSpy).toHaveBeenCalledWith(
      expect.stringContaining('[cerrarTurnoChain]'),
      expect.anything(),
    );
    expect(cerrarSesion).not.toHaveBeenCalled();
  });

  it('justificacion_requerida (400) → console.error + kind justificacion_requerida', async () => {
    const submitArqueo = vi.fn().mockRejectedValue(
      new ParkosHttpError(400, JSON.stringify({ detail: { error: 'justificacion_requerida' } }), '/caja/arqueo'),
    );
    const cerrarSesion = vi.fn();

    const result = await runCerrarTurnoChain({
      ...baseArgs(),
      submitArqueo,
      cerrarSesion,
    });

    expect(result).toEqual({ kind: 'justificacion_requerida' });
    expect(consoleErrorSpy).toHaveBeenCalled();
    expect(cerrarSesion).not.toHaveBeenCalled();
  });

  it('arqueo_fallido (5xx) → console.error + kind arqueo_fallido with status', async () => {
    const submitArqueo = vi.fn().mockRejectedValue(
      new ParkosHttpError(500, JSON.stringify({ detail: { error: 'server_error' } }), '/caja/arqueo'),
    );
    const cerrarSesion = vi.fn();

    const result = await runCerrarTurnoChain({
      ...baseArgs(),
      submitArqueo,
      cerrarSesion,
    });

    expect(result).toEqual({ kind: 'arqueo_fallido', status: 500 });
    expect(consoleErrorSpy).toHaveBeenCalled();
  });

  it('arqueo_fallido (unknown thrown value) → console.error + status 0', async () => {
    const submitArqueo = vi.fn().mockRejectedValue('boom');
    const cerrarSesion = vi.fn();

    const result = await runCerrarTurnoChain({
      ...baseArgs(),
      submitArqueo,
      cerrarSesion,
    });

    expect(result).toEqual({ kind: 'arqueo_fallido', status: 0 });
    expect(consoleErrorSpy).toHaveBeenCalled();
  });

  it('cierre 404 (sesion_not_found) → console.error + kind redirect_login', async () => {
    const submitArqueo = vi.fn().mockResolvedValue({ uuid: 'arqueo-uuid-1' });
    const cerrarSesion = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      error: { code: 'sesion_not_found' },
    });

    const result = await runCerrarTurnoChain({
      ...baseArgs(),
      submitArqueo,
      cerrarSesion,
    });

    expect(result).toEqual({ kind: 'redirect_login' });
    expect(consoleErrorSpy).toHaveBeenCalled();
  });

  it('cierre 409 (ya cerrado) → console.error + kind cierre_ya_cerrado with uuid_arqueo', async () => {
    const submitArqueo = vi.fn().mockResolvedValue({ uuid: 'arqueo-uuid-1' });
    const cerrarSesion = vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
      error: { code: 'sesion_ya_cerrada' },
    });

    const result = await runCerrarTurnoChain({
      ...baseArgs(),
      submitArqueo,
      cerrarSesion,
    });

    expect(result).toEqual({ kind: 'cierre_ya_cerrado', uuid_arqueo: 'arqueo-uuid-1' });
    expect(consoleErrorSpy).toHaveBeenCalled();
  });

  it('cierre 5xx → console.error + kind cierre_fallido with uuid_arqueo', async () => {
    const submitArqueo = vi.fn().mockResolvedValue({ uuid: 'arqueo-uuid-1' });
    const cerrarSesion = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      error: { code: 'server_error' },
    });

    const result = await runCerrarTurnoChain({
      ...baseArgs(),
      submitArqueo,
      cerrarSesion,
    });

    expect(result).toEqual({ kind: 'cierre_fallido', uuid_arqueo: 'arqueo-uuid-1' });
    expect(consoleErrorSpy).toHaveBeenCalled();
  });

  it('success path → no console.error at all', async () => {
    const submitArqueo = vi.fn().mockResolvedValue({ uuid: 'arqueo-uuid-1' });
    const cerrarSesion = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      sesion: { ...SESION, timestamp_cierre: '2026-09-21T18:00:00Z' },
    });

    const result = await runCerrarTurnoChain({
      ...baseArgs(),
      submitArqueo,
      cerrarSesion,
    });

    expect(result.kind).toBe('redirect_login_closed');
    expect(consoleErrorSpy).not.toHaveBeenCalled();
  });
});
