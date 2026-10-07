/**
 * `cierreDiarioChain.test.ts` — Strict-TDD RED scaffold for HU-F10.3
 * (REQ-OPS-166, AD-2).
 *
 * 2-step sequencer (POST /caja/arqueo + imprimirCierre) that mirrors
 * F10.2's `cerrarTurnoChain.ts` (REQ-OPS-159) but FLATTENED to
 * 2 steps because the backend `cerrar_sesiones_del_dia_bulk` (KD-ARQUEO-03,
 * triggered at `caja_arqueo.py:266-272`) handles per-session closure
 * in-tx. NO PUT sesion-close; NO client-side DELETE on `[A]` tables.
 *
 * The discriminated result envelope has 5 kinds per REQ-OPS-166:
 *   - 'success' — happy path (imprimirCierre failure is non-fatal)
 *   - 'arqueo_fallido' — POST 4xx/5xx (ParkosHttpError)
 *   - 'red_arqueo' — POST TypeError (network)
 *   - 'ya_cerrado' — POST 409 closure already exists (defensive)
 *   - 'permiso_insuficiente' — POST 403 tenant_scope_violation
 *
 * Scenarios (5):
 *   chain-1 — happy 2-step: POST 201 + imprimirCierre once →
 *             { kind: 'success', uuid_arqueo: 'AD' }
 *   chain-2 — bridge failure non-fatal: POST 201 + imprimirCierre
 *             rejects → still { kind: 'success', uuid_arqueo: 'AD' } +
 *             console.warn observability (DA-F10.3-6 RESOLVED).
 *   chain-3 — POST 400 `cierre_dia_no_acepta_uuid_sesion` →
 *             { kind: 'arqueo_fallido', status: 400 } — programmer
 *             error indicator (the FE never passes uuid_sesion).
 *   chain-4 — POST 5xx → { kind: 'arqueo_fallido', status: 500 }
 *             NO imprimirCierre fires.
 *   chain-5 — POST network TypeError → { kind: 'red_arqueo' }
 *             NO imprimirCierre fires.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import {
  runCierreDiarioChain,
  type ArqueoSubmitFn,
} from '../cierreDiarioChain';

let submitArqueo: ReturnType<typeof vi.fn>;
let imprimirCierre: ReturnType<typeof vi.fn>;

const TIPO_CIERRE_DIA_UUID = '6a759c41-1896-4362-bde4-6eff00ae6626';

const BASE_VALUES = {
  valor_efectivo_reportado: 150_000,
};

beforeEach(() => {
  submitArqueo = vi.fn();
  imprimirCierre = vi.fn();
});

afterEach(() => {
  vi.clearAllMocks();
});

const chain = (values: unknown = BASE_VALUES) =>
  runCierreDiarioChain({
    submitArqueo: submitArqueo as unknown as ArqueoSubmitFn,
    uuidTipoArqueo: TIPO_CIERRE_DIA_UUID,
    imprimirCierre,
    values: values as never,
  });

describe('HU-F10.3 — cierreDiarioChain (REQ-OPS-166, AD-2)', () => {
  // ──────────────────────────────────────────────────────────────────
  // chain-1 — happy path 2-step sequencer
  // ──────────────────────────────────────────────────────────────────
  it('chain-1: happy 2-step sequencer POST 201 + imprimirCierre once → { kind: "success", uuid_arqueo: "AD" }', async () => {
    submitArqueo.mockResolvedValueOnce({ uuid: 'arqueo-uuid-AD' });

    const result = await chain();

    expect(submitArqueo).toHaveBeenCalledTimes(1);
    // Wire body MUST carry the resolved `uuid_tipo_arqueo` (the V2 schema
    // forbids the legacy `tipo_arqueo` codigo string: 422 extra_forbidden)
    // and `uuid_sesion: null` (cierre_dia has no sesion).
    expect(submitArqueo).toHaveBeenCalledWith({
      uuid_sesion: null,
      uuid_tipo_arqueo: TIPO_CIERRE_DIA_UUID,
      valor_efectivo_reportado: 150_000,
    });
    expect(submitArqueo.mock.calls[0]?.[0]).not.toHaveProperty('tipo_arqueo');
    // the slip data is handed over exactly once (real print lives in the orchestrator).
    expect(imprimirCierre).toHaveBeenCalledTimes(1);
    expect(imprimirCierre).toHaveBeenCalledWith({
      arqueo: { uuid: 'arqueo-uuid-AD' },
      valor_efectivo_reportado: 150_000,
      justificacion: undefined,
    });
    expect(result).toEqual({
      kind: 'success',
      uuid_arqueo: 'arqueo-uuid-AD',
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // chain-2 — bridge failure non-fatal (DA-F10.3-6 RESOLVED)
  // ──────────────────────────────────────────────────────────────────
  it('chain-2: imprimirCierre rejects → still { kind: "success" } + console.warn "escpos_printer_offline"', async () => {
    submitArqueo.mockResolvedValueOnce({ uuid: 'arqueo-uuid-AD' });
    const warnSpy = vi
      .spyOn(console, 'warn')
      .mockImplementation(() => undefined);
    imprimirCierre.mockRejectedValueOnce(new Error('printer offline'));

    const result = await chain();
    await Promise.resolve();

    // Non-fatal: result MUST still be success.
    expect(result).toEqual({
      kind: 'success',
      uuid_arqueo: 'arqueo-uuid-AD',
    });
    // Observability: console.warn fired with literal prefix.
    const warnCalls = warnSpy.mock.calls.map((call) => String(call[0]));
    expect(
      warnCalls.some((msg) => msg.startsWith('escpos_printer_offline')),
    ).toBe(true);
    warnSpy.mockRestore();
  });

  // ──────────────────────────────────────────────────────────────────
  // chain-3 — POST 400 cierre_dia_no_acepta_uuid_sesion surfaces drift
  // ──────────────────────────────────────────────────────────────────
  it('chain-3: POST 400 cierre_dia_no_acepta_uuid_sesion → { kind: "arqueo_fallido", status: 400 } (programmer-error indicator)', async () => {
    submitArqueo.mockRejectedValueOnce(
      new ParkosHttpError(
        400,
        'cierre_dia_no_acepta_uuid_sesion',
        'cierre_dia_no_acepta_uuid_sesion',
      ),
    );

    const result = await chain();

    // NO imprimirCierre on failure.
    expect(imprimirCierre).not.toHaveBeenCalled();
    expect(result).toEqual({
      kind: 'arqueo_fallido',
      status: 400,
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // chain-4 — POST 5xx leaves S3 OPEN (KD-ARQUEO-01 atomicity)
  // ──────────────────────────────────────────────────────────────────
  it('chain-4: POST 5xx → { kind: "arqueo_fallido", status: 500 } (NO imprimirCierre, NO retry)', async () => {
    submitArqueo.mockRejectedValueOnce(
      new ParkosHttpError(500, 'internal_server_error', 'internal_error'),
    );

    const result = await chain();

    expect(imprimirCierre).not.toHaveBeenCalled();
    expect(result).toEqual({
      kind: 'arqueo_fallido',
      status: 500,
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // chain-5 — POST network TypeError → { kind: 'red_arqueo' }
  // ──────────────────────────────────────────────────────────────────
  it('chain-5: POST network TypeError → { kind: "red_arqueo" } (NO imprimirCierre)', async () => {
    submitArqueo.mockRejectedValueOnce(new TypeError('NetworkError'));

    const result = await chain();

    expect(imprimirCierre).not.toHaveBeenCalled();
    expect(result).toEqual({ kind: 'red_arqueo' });
  });

  // ──────────────────────────────────────────────────────────────────
  // chain-6 — server error detail is surfaced (H9: no more generic banner)
  // ──────────────────────────────────────────────────────────────────
  it('chain-6: POST 422 FastAPI validation body → arqueo_fallido with readable detail', async () => {
    const body = JSON.stringify({
      detail: [
        {
          type: 'missing',
          loc: ['body', 'uuid_tipo_arqueo'],
          msg: 'Field required',
        },
      ],
    });
    submitArqueo.mockRejectedValueOnce(
      new ParkosHttpError(422, body, '/api/v1/caja/arqueo'),
    );

    const result = await chain();

    expect(result).toEqual({
      kind: 'arqueo_fallido',
      status: 422,
      detail: 'body.uuid_tipo_arqueo: Field required',
    });
  });

  it('chain-7: POST 400 {detail:{error}} → arqueo_fallido with the error code as detail', async () => {
    submitArqueo.mockRejectedValueOnce(
      new ParkosHttpError(
        400,
        JSON.stringify({ detail: { error: 'justificacion_requerida' } }),
        '/api/v1/caja/arqueo',
      ),
    );

    const result = await chain();

    expect(result).toEqual({
      kind: 'arqueo_fallido',
      status: 400,
      detail: 'justificacion_requerida',
    });
  });
});
