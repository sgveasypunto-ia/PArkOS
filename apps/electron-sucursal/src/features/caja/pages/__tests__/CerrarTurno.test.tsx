/**
 * `CerrarTurno.test.tsx` — Strict-TDD unit tests for HU-F10.2
 * (REQ-OPS-157, REQ-OPS-159, AD-2 + AD-3 + AD-5 + AD-6).
 *
 * The 3-step sequencer lives in `./cerrarTurnoChain.ts` as a pure
 * helper so we can test the precedence exhaustively without
 * wrestling with react-hook-form + `@testing-library/user-event`
 * (which is unavailable in this sandbox, per F9.x precedent).
 *
 * Coverage (10):
 *   1. happy path POST 201 + bridge.imprimir fires once + PUT 200 + redirect /login?closed=true.
 *   2. happy path |diferencia|=0: justificacion dropped from POST body.
 *   3. happy path |diferencia|>0: justificacion included in POST body.
 *   4. POST 5xx → arqueo_fallido, NO bridge.imprimir, NO PUT call.
 *   5. POST network → red_arqueo, NO bridge.imprimir, NO PUT call.
 *   6. POST 400 arqueo_invalid → arqueo_fallido (terminal).
 *   7. PUT 404 SesionAlreadyClosedError → redirect_login (no ?closed=true).
 *   8. PUT 409 sesion_ya_cerrada → cierre_ya_cerrado + uuid_arqueo surfaced.
 *   9. PUT 5xx → cierre_fallido + uuid_arqueo surfaced.
 *  10. PUT 401 → F3.3 fallback: redirect_login (no ?closed=true).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

import {
  runCerrarTurnoChain,
  type ArqueoSubmitFn,
  type CerrarSesionHelper,
  type CerrarTurnoBridge,
} from '../cerrarTurnoChain';
import type { SesionRead } from '../../api/sesionActivaApi';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

const SESION: SesionRead = {
  uuid: 'sess-uuid-1',
  uuid_sucursal: 'suc-uuid-1',
  uuid_usuario: 'usr-uuid-1',
  valor_inicial_efectivo: 50_000,
  valor_inicial_datafono: 0,
  timestamp_apertura: '2026-09-21T08:00:00Z',
  timestamp_cierre: null,
};

const BASE_VALUES = {
  valor_efectivo_reportado: 100_000,
  valor_datafono_reportado: 0,
};

let submitArqueo: ReturnType<typeof vi.fn>;
let cerrarSesion: ReturnType<typeof vi.fn>;
let bridge: CerrarTurnoBridge;

beforeEach(() => {
  submitArqueo = vi.fn();
  cerrarSesion = vi.fn();
  bridge = { imprimir: vi.fn() };
});

const UUID_TIPO_CIERRE_TURNO = 'tipo-arqueo-uuid-cierre-turno';

const chain = (values: unknown = BASE_VALUES) =>
  runCerrarTurnoChain({
    sesion: SESION,
    uuidTipoArqueo: UUID_TIPO_CIERRE_TURNO,
    submitArqueo: submitArqueo as unknown as ArqueoSubmitFn,
    cerrarSesion: cerrarSesion as unknown as CerrarSesionHelper,
    bridge,
    values: values as never,
  });

describe('HU-F10.2 — cerrarTurnoChain (REQ-OPS-157, REQ-OPS-159, AD-2 + AD-3)', () => {
  // ────────────────────────────────────────────────────────────────────
  // seq-1-happy-path — POST 201 → bridge.imprimir → PUT 200 → redirect
  // ────────────────────────────────────────────────────────────────────
  it('seq-1: happy path POST 201 + bridge.imprimir once + PUT 200 → redirect /login?closed=true', async () => {
    submitArqueo.mockResolvedValueOnce({ uuid: 'arqueo-uuid-1' });
    cerrarSesion.mockResolvedValueOnce({
      ok: true,
      status: 200,
      sesion: { ...SESION, timestamp_cierre: '2026-09-21T18:00:00Z' },
    });

    const result = await chain();

    // 1. arqueo submit was awaited FIRST with cierre_turno discriminator.
    expect(submitArqueo).toHaveBeenCalledTimes(1);
    expect(submitArqueo).toHaveBeenCalledWith({
      uuid_sesion: 'sess-uuid-1',
      uuid_tipo_arqueo: UUID_TIPO_CIERRE_TURNO,
      valor_efectivo_reportado: 100_000,
      valor_datafono_reportado: 0,
    });

    // 2. bridge.imprimir fired exactly once with auditoria_codigo='cierre_turno'.
    expect(bridge.imprimir).toHaveBeenCalledTimes(1);
    expect(bridge.imprimir).toHaveBeenCalledWith(
      'arqueo',
      expect.objectContaining({
        uuid: 'arqueo-uuid-1',
        auditoria_codigo: 'cierre_turno',
      }),
    );

    // 3. THEN the helper is invoked (after POST + bridge.imprimir).
    expect(cerrarSesion).toHaveBeenCalledTimes(1);
    expect(cerrarSesion).toHaveBeenCalledWith('sess-uuid-1', {
      valor_final_efectivo: 100_000,
      valor_final_datafono: 0,
    });

    expect(result).toEqual({
      kind: 'redirect_login_closed',
      sesion: expect.objectContaining({
        uuid: 'sess-uuid-1',
        timestamp_cierre: '2026-09-21T18:00:00Z',
      }),
    });
  });

  // ────────────────────────────────────────────────────────────────────
  // seq-1b-no-duplicate-input — valor_final_* is DERIVED from the
  // reportado fields, never asked as separate input (fix: cierre de
  // turno ya no pide el mismo conteo físico dos veces).
  // ────────────────────────────────────────────────────────────────────
  it('seq-1b: valor_final_* is derived from valor_*_reportado (no duplicate input)', async () => {
    submitArqueo.mockResolvedValueOnce({ uuid: 'arqueo-uuid-1b' });
    cerrarSesion.mockResolvedValueOnce({
      ok: true,
      status: 200,
      sesion: SESION,
    });

    await chain({
      valor_efectivo_reportado: 97_500,
      valor_datafono_reportado: 3_200,
    });

    expect(cerrarSesion).toHaveBeenCalledWith('sess-uuid-1', {
      valor_final_efectivo: 97_500,
      valor_final_datafono: 3_200,
    });
  });

  // ────────────────────────────────────────────────────────────────────
  // seq-2-tolerancia — |diferencia|=0: justificacion DROPPED from POST body
  // ────────────────────────────────────────────────────────────────────
  it('seq-2: |diferencia|=0 → justificacion dropped from POST body', async () => {
    submitArqueo.mockResolvedValueOnce({ uuid: 'arqueo-uuid-2' });
    cerrarSesion.mockResolvedValueOnce({
      ok: true,
      status: 200,
      sesion: SESION,
    });

    await chain({
      ...BASE_VALUES,
      valor_efectivo_reportado: 100_000,
      valor_datafono_reportado: 0,
      justificacion: '',
    });

    const callArg = submitArqueo.mock.calls[0]?.[0] as Record<string, unknown>;
    expect(callArg).not.toHaveProperty('justificacion');
  });

  // ────────────────────────────────────────────────────────────────────
  // seq-3-diferencia-fuera-tolerancia — justificacion REQUIRED + included
  // ────────────────────────────────────────────────────────────────────
  it('seq-3: justificacion non-empty → included in POST body + trim applied', async () => {
    submitArqueo.mockResolvedValueOnce({ uuid: 'arqueo-uuid-3' });
    cerrarSesion.mockResolvedValueOnce({
      ok: true,
      status: 200,
      sesion: SESION,
    });

    await chain({
      ...BASE_VALUES,
      valor_efectivo_reportado: 97_000,
      valor_datafono_reportado: 0,
      justificacion: '  Faltante menor en caja  ',
    });

    expect(submitArqueo).toHaveBeenCalledWith(
      expect.objectContaining({
        valor_efectivo_reportado: 97_000,
        justificacion: 'Faltante menor en caja',
      }),
    );
  });

  // ────────────────────────────────────────────────────────────────────
  // post-3-5xx-no-cerrarsesion — POST 5xx → arqueo_fallido
  // ────────────────────────────────────────────────────────────────────
  it('post-3: POST 5xx → arqueo_fallido, NO bridge.imprimir, NO cerrarSesion', async () => {
    submitArqueo.mockRejectedValueOnce(
      new ParkosHttpError(500, '{"error":"server_error"}', '/api/v1/caja/arqueo'),
    );

    const result = await chain();

    expect(result).toEqual({ kind: 'arqueo_fallido', status: 500 });
    expect(bridge.imprimir).not.toHaveBeenCalled();
    expect(cerrarSesion).not.toHaveBeenCalled();
  });

  // ────────────────────────────────────────────────────────────────────
  // post-4-network-no-cerrarsesion — POST network → red_arqueo
  // ────────────────────────────────────────────────────────────────────
  it('post-4: POST network error → red_arqueo, NO bridge.imprimir, NO cerrarSesion', async () => {
    submitArqueo.mockRejectedValueOnce(new TypeError('Failed to fetch'));

    const result = await chain();

    expect(result).toEqual({ kind: 'red_arqueo' });
    expect(bridge.imprimir).not.toHaveBeenCalled();
    expect(cerrarSesion).not.toHaveBeenCalled();
  });

  // ────────────────────────────────────────────────────────────────────
  // post-2-400-arqueo-invalid — POST 400 → arqueo_fallido (terminal)
  // ────────────────────────────────────────────────────────────────────
  it('post-2: POST 400 arqueo_invalid → arqueo_fallido, NO cerrarSesion', async () => {
    submitArqueo.mockRejectedValueOnce(
      new ParkosHttpError(
        400,
        '{"error":"arqueo_invalid","campo":["valor_efectivo_reportado"]}',
        '/api/v1/caja/arqueo',
      ),
    );

    const result = await chain();

    expect(result).toEqual({ kind: 'arqueo_fallido', status: 400 });
    expect(cerrarSesion).not.toHaveBeenCalled();
  });

  // ────────────────────────────────────────────────────────────────────
  // put-1-404-sesion-not-found → redirect_login (no ?closed=true)
  // ────────────────────────────────────────────────────────────────────
  it('put-1: PUT 404 SesionAlreadyClosedError → redirect_login (no ?closed=true)', async () => {
    submitArqueo.mockResolvedValueOnce({ uuid: 'arqueo-uuid-A' });
    cerrarSesion.mockResolvedValueOnce({
      ok: false,
      status: 404,
      error: new Error('sesion_not_found'),
    });

    const result = await chain();

    expect(result).toEqual({ kind: 'redirect_login' });
    // bridge.imprimir fires BEFORE the PUT attempt (REQ-OPS-157 happy).
    expect(bridge.imprimir).toHaveBeenCalledTimes(1);
  });

  // ────────────────────────────────────────────────────────────────────
  // put-2-409-sesion-ya-cerrada — orphan uuid surfaced, NO clear, NO navigate
  // ────────────────────────────────────────────────────────────────────
  it('put-2: PUT 409 sesion_ya_cerrada → cierre_ya_cerrado + uuid_arqueo surfaced', async () => {
    submitArqueo.mockResolvedValueOnce({ uuid: 'arqueo-uuid-orphan' });
    cerrarSesion.mockResolvedValueOnce({
      ok: false,
      status: 409,
      error: new ParkosHttpError(
        409,
        '{"error":"sesion_ya_cerrada"}',
        '/api/v1/caja-sesion/sesion/sess-uuid-1/cerrar',
      ),
    });

    const result = await chain();

    // The orphan uuid MUST be surfaced for the supervisor remediation
    // banner (REQ-OPS-159 case 6 + ABBC-F10.2-BE-1).
    expect(result).toEqual({
      kind: 'cierre_ya_cerrado',
      uuid_arqueo: 'arqueo-uuid-orphan',
    });
  });

  // ────────────────────────────────────────────────────────────────────
  // put-3-5xx-orphan-uuid — PUT 5xx → cierre_fallido + uuid_arqueo surfaced
  // ────────────────────────────────────────────────────────────────────
  it('put-3: PUT 5xx → cierre_fallido + uuid_arqueo surfaced', async () => {
    submitArqueo.mockResolvedValueOnce({ uuid: 'arqueo-uuid-5xx' });
    cerrarSesion.mockResolvedValueOnce({
      ok: false,
      status: 500,
      error: new ParkosHttpError(
        500,
        '{"error":"server_error"}',
        '/api/v1/caja-sesion/sesion/sess-uuid-1/cerrar',
      ),
    });

    const result = await chain();

    expect(result).toEqual({
      kind: 'cierre_fallido',
      uuid_arqueo: 'arqueo-uuid-5xx',
    });
  });

  // ────────────────────────────────────────────────────────────────────
  // put-4-401-f3.3-fallback → redirect_login (helper did clear+event)
  // ────────────────────────────────────────────────────────────────────
  it('put-4: PUT 401 → F3.3 fallback redirect_login (no ?closed=true)', async () => {
    submitArqueo.mockResolvedValueOnce({ uuid: 'arqueo-uuid-401' });
    cerrarSesion.mockResolvedValueOnce({
      ok: false,
      status: 401,
      error: new ParkosHttpError(
        401,
        '{"error":"unauthorized"}',
        '/api/v1/caja-sesion/sesion/sess-uuid-1/cerrar',
      ),
    });

    const result = await chain();

    expect(result).toEqual({ kind: 'redirect_login' });
  });

  // ────────────────────────────────────────────────────────────────────
  // no-retry-1 — orchestrator does NOT retry arqueo.submit on failure
  // ────────────────────────────────────────────────────────────────────
  it('no-retry: orchestrator does NOT retry arqueo.submit on failure', async () => {
    submitArqueo.mockRejectedValueOnce(
      new ParkosHttpError(500, '{"error":"server_error"}', '/api/v1/caja/arqueo'),
    );

    await chain();

    expect(submitArqueo).toHaveBeenCalledTimes(1);
    expect(bridge.imprimir).not.toHaveBeenCalled();
    expect(cerrarSesion).not.toHaveBeenCalled();
  });
});