/**
 * `cierreDiarioChain.test.ts` — Strict-TDD RED scaffold for HU-F10.3
 * (REQ-OPS-166, AD-2).
 *
 * 2-step sequencer (POST /caja/arqueo + bridge.imprimir) that mirrors
 * F10.2's `cerrarTurnoChain.ts` (REQ-OPS-159) but FLATTENED to
 * 2 steps because the backend `cerrar_sesiones_del_dia_bulk` (KD-ARQUEO-03,
 * triggered at `caja_arqueo.py:266-272`) handles per-session closure
 * in-tx. NO PUT sesion-close; NO client-side DELETE on `[A]` tables.
 *
 * The discriminated result envelope has 5 kinds per REQ-OPS-166:
 *   - 'success' — happy path (bridge.imprimir failure is non-fatal)
 *   - 'arqueo_fallido' — POST 4xx/5xx (ParkosHttpError)
 *   - 'red_arqueo' — POST TypeError (network)
 *   - 'ya_cerrado' — POST 409 closure already exists (defensive)
 *   - 'permiso_insuficiente' — POST 403 tenant_scope_violation
 *
 * Scenarios (5):
 *   chain-1 — happy 2-step: POST 201 + bridge.imprimir once →
 *             { kind: 'success', uuid_arqueo: 'AD' }
 *   chain-2 — bridge failure non-fatal: POST 201 + bridge.imprimir
 *             rejects → still { kind: 'success', uuid_arqueo: 'AD' } +
 *             console.warn observability (DA-F10.3-6 RESOLVED).
 *   chain-3 — POST 400 `cierre_dia_no_acepta_uuid_sesion` →
 *             { kind: 'arqueo_fallido', status: 400 } — programmer
 *             error indicator (the FE never passes uuid_sesion).
 *   chain-4 — POST 5xx → { kind: 'arqueo_fallido', status: 500 }
 *             NO bridge.imprimir fires.
 *   chain-5 — POST network TypeError → { kind: 'red_arqueo' }
 *             NO bridge.imprimir fires.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import {
  runCierreDiarioChain,
  type ArqueoSubmitFn,
  type CierreDiarioBridge,
} from '../cierreDiarioChain';

let submitArqueo: ReturnType<typeof vi.fn>;
let bridge: CierreDiarioBridge;

const BASE_VALUES = {
  valor_efectivo_reportado: 150_000,
  valor_datafono_reportado: 30_000,
};

beforeEach(() => {
  submitArqueo = vi.fn();
  bridge = { imprimir: vi.fn() };
});

afterEach(() => {
  vi.clearAllMocks();
});

const chain = (values: unknown = BASE_VALUES) =>
  runCierreDiarioChain({
    submitArqueo: submitArqueo as unknown as ArqueoSubmitFn,
    bridge,
    values: values as never,
  });

describe('HU-F10.3 — cierreDiarioChain (REQ-OPS-166, AD-2)', () => {
  // ──────────────────────────────────────────────────────────────────
  // chain-1 — happy path 2-step sequencer
  // ──────────────────────────────────────────────────────────────────
  it('chain-1: happy 2-step sequencer POST 201 + bridge.imprimir once → { kind: "success", uuid_arqueo: "AD" }', async () => {
    submitArqueo.mockResolvedValueOnce({ uuid: 'arqueo-uuid-AD' });

    const result = await chain();

    expect(submitArqueo).toHaveBeenCalledTimes(1);
    // Wire body MUST carry uuid_sesion: null (corrigendum for the
    // buggy useCierreDiario() at useArqueo.ts:107-117).
    expect(submitArqueo).toHaveBeenCalledWith({
      uuid_sesion: null,
      tipo_arqueo: 'cierre_dia',
      valor_efectivo_reportado: 150_000,
      valor_datafono_reportado: 30_000,
    });
    // bridge.imprimir fired exactly once with auditoria_codigo='cierre_dia'.
    expect(bridge.imprimir).toHaveBeenCalledTimes(1);
    expect(bridge.imprimir).toHaveBeenCalledWith(
      'arqueo',
      expect.objectContaining({
        uuid: 'arqueo-uuid-AD',
        auditoria_codigo: 'cierre_dia',
      }),
    );
    expect(result).toEqual({
      kind: 'success',
      uuid_arqueo: 'arqueo-uuid-AD',
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // chain-2 — bridge failure non-fatal (DA-F10.3-6 RESOLVED)
  // ──────────────────────────────────────────────────────────────────
  it('chain-2: bridge.imprimir rejects → still { kind: "success" } + console.warn "escpos_printer_offline"', async () => {
    submitArqueo.mockResolvedValueOnce({ uuid: 'arqueo-uuid-AD' });
    const warnSpy = vi
      .spyOn(console, 'warn')
      .mockImplementation(() => undefined);
    (bridge.imprimir as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error('printer offline'),
    );

    const result = await chain();

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

    // NO bridge.imprimir on failure.
    expect(bridge.imprimir).not.toHaveBeenCalled();
    expect(result).toEqual({
      kind: 'arqueo_fallido',
      status: 400,
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // chain-4 — POST 5xx leaves S3 OPEN (KD-ARQUEO-01 atomicity)
  // ──────────────────────────────────────────────────────────────────
  it('chain-4: POST 5xx → { kind: "arqueo_fallido", status: 500 } (NO bridge.imprimir, NO retry)', async () => {
    submitArqueo.mockRejectedValueOnce(
      new ParkosHttpError(500, 'internal_server_error', 'internal_error'),
    );

    const result = await chain();

    expect(bridge.imprimir).not.toHaveBeenCalled();
    expect(result).toEqual({
      kind: 'arqueo_fallido',
      status: 500,
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // chain-5 — POST network TypeError → { kind: 'red_arqueo' }
  // ──────────────────────────────────────────────────────────────────
  it('chain-5: POST network TypeError → { kind: "red_arqueo" } (NO bridge.imprimir)', async () => {
    submitArqueo.mockRejectedValueOnce(new TypeError('NetworkError'));

    const result = await chain();

    expect(bridge.imprimir).not.toHaveBeenCalled();
    expect(result).toEqual({ kind: 'red_arqueo' });
  });
});