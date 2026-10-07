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
  observaciones_cierre: '',
};

const baseArgs = () => ({
  sesion: SESION,
  uuidTipoArqueo: 'tipo-arqueo-uuid-1',
  imprimirCierre: null,
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

  it('success path → no console.error at all, hands back data for the summary (PT-5)', async () => {
    const arqueo = {
      uuid: 'arqueo-uuid-1',
      valor_efectivo_esperado: 120_000,
      valor_efectivo_reportado: 100_000,
      diferencia_efectivo: -20_000,
    };
    const submitArqueo = vi.fn().mockResolvedValue(arqueo);
    const closed = { ...SESION, timestamp_cierre: '2026-09-21T18:00:00Z' };
    const cerrarSesion = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      sesion: closed,
    });

    const result = await runCerrarTurnoChain({
      ...baseArgs(),
      values: { ...BASE_VALUES, observaciones_cierre: '  Faltante  ' },
      submitArqueo,
      cerrarSesion,
    });

    expect(result).toEqual({
      kind: 'cierre_completado',
      sesion: closed,
      arqueo,
      observaciones: 'Faltante',
    });
    expect(consoleErrorSpy).not.toHaveBeenCalled();
  });

  it('PT-5: the PUT defers the logout so the summary can be shown first', async () => {
    const submitArqueo = vi.fn().mockResolvedValue({ uuid: 'arqueo-uuid-1' });
    const cerrarSesion = vi
      .fn()
      .mockResolvedValue({ ok: true, status: 200, sesion: { ...SESION } });

    await runCerrarTurnoChain({ ...baseArgs(), submitArqueo, cerrarSesion });

    expect(cerrarSesion).toHaveBeenCalledWith(
      SESION.uuid,
      { valor_final_efectivo: 100_000 },
      { deferLogout: true },
    );
  });

  it('PT-4/PT-6: with a difference the backend 400s and the chain retries ONCE with Observaciones as `justificacion`; no datáfono on the wire', async () => {
    consoleErrorSpy.mockClear();
    const submitArqueo = vi
      .fn()
      .mockRejectedValueOnce(
        new ParkosHttpError(
          400,
          JSON.stringify({ detail: { error: 'justificacion_requerida' } }),
          '/caja/arqueo',
        ),
      )
      .mockResolvedValueOnce({ uuid: 'arqueo-uuid-1' });
    const cerrarSesion = vi
      .fn()
      .mockResolvedValue({ ok: true, status: 200, sesion: { ...SESION } });

    const result = await runCerrarTurnoChain({
      ...baseArgs(),
      values: { valor_efectivo_reportado: 90_000, observaciones_cierre: '  Billete falso ' },
      submitArqueo,
      cerrarSesion,
    });

    expect(result.kind).toBe('cierre_completado');
    expect(submitArqueo).toHaveBeenCalledTimes(2);
    expect(submitArqueo.mock.calls[0]?.[0]).toEqual({
      uuid_sesion: SESION.uuid,
      uuid_tipo_arqueo: 'tipo-arqueo-uuid-1',
      valor_efectivo_reportado: 90_000,
    });
    expect(submitArqueo.mock.calls[1]?.[0]).toEqual({
      uuid_sesion: SESION.uuid,
      uuid_tipo_arqueo: 'tipo-arqueo-uuid-1',
      valor_efectivo_reportado: 90_000,
      justificacion: 'Billete falso',
    });
    expect(cerrarSesion).toHaveBeenCalledWith(
      SESION.uuid,
      { valor_final_efectivo: 90_000, observaciones_cierre: '  Billete falso ' },
      { deferLogout: true },
    );
  });

  it('PT-4: balanced close sends NO `justificacion` even when Observaciones has a note (REQ-OPS-157), in a single POST', async () => {
    const submitArqueo = vi.fn().mockResolvedValue({ uuid: 'arqueo-uuid-1' });
    const cerrarSesion = vi
      .fn()
      .mockResolvedValue({ ok: true, status: 200, sesion: { ...SESION } });

    await runCerrarTurnoChain({
      ...baseArgs(),
      values: { valor_efectivo_reportado: 100_000, observaciones_cierre: 'Nota de relevo' },
      submitArqueo,
      cerrarSesion,
    });

    expect(submitArqueo).toHaveBeenCalledTimes(1);
    const body = submitArqueo.mock.calls[0]?.[0] as Record<string, unknown>;
    expect('justificacion' in body).toBe(false);
    expect('valor_datafono_reportado' in body).toBe(false);
  });

  it('PT-4: 400 justificacion_requerida with NO Observaciones → no retry, kind justificacion_requerida', async () => {
    const submitArqueo = vi.fn().mockRejectedValue(
      new ParkosHttpError(
        400,
        JSON.stringify({ detail: { error: 'justificacion_requerida' } }),
        '/caja/arqueo',
      ),
    );
    const cerrarSesion = vi.fn();

    const result = await runCerrarTurnoChain({ ...baseArgs(), submitArqueo, cerrarSesion });

    expect(result).toEqual({ kind: 'justificacion_requerida' });
    expect(submitArqueo).toHaveBeenCalledTimes(1);
    expect(cerrarSesion).not.toHaveBeenCalled();
  });

  it('PT-4: a second 400 after the retry is surfaced, never looped', async () => {
    const err = () =>
      new ParkosHttpError(
        400,
        JSON.stringify({ detail: { error: 'justificacion_requerida' } }),
        '/caja/arqueo',
      );
    const submitArqueo = vi.fn().mockRejectedValueOnce(err()).mockRejectedValueOnce(err());
    const cerrarSesion = vi.fn();

    const result = await runCerrarTurnoChain({
      ...baseArgs(),
      values: { valor_efectivo_reportado: 1, observaciones_cierre: 'motivo' },
      submitArqueo,
      cerrarSesion,
    });

    expect(result).toEqual({ kind: 'justificacion_requerida' });
    expect(submitArqueo).toHaveBeenCalledTimes(2);
  });
});
