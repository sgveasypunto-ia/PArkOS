/**
 * `cerrarTurnoChain.test.ts` — dedicated coverage for the
 * `justificacion_requerida` detection branch (REGRESSION, 2026-09-25).
 *
 * Real bug found live: the backend computes the true expected total
 * (opening float + the shift's transactions) server-side only —
 * `CerrarTurnoForm.tsx`'s client-side `hayDiferencia` heuristic compares
 * against `sesion.valor_inicial_*` instead, so it can under-detect a
 * real difference and never render the Justificación field. Every
 * retry then sent the identical payload (same idempotency-key) and got
 * rejected forever with `{"detail":{"error":"justificacion_requerida"}}`,
 * with no way to recover from the UI.
 *
 * `runCerrarTurnoChain` now distinguishes this specific backend rejection
 * from any other arqueo failure so `<CerrarTurno>` can force the field
 * to render regardless of the client's own guess (see CerrarTurno.tsx +
 * CerrarTurnoForm.tsx's `forceRequireJustificacion`).
 *
 * The other 7 precedence cases already have a pre-existing coverage gap
 * (see CerrarTurno.test.tsx's header comment) — out of scope here.
 */
import { describe, it, expect, vi } from 'vitest';

import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import { runCerrarTurnoChain } from './cerrarTurnoChain';
import type { SesionRead } from '../api/sesionActivaApi';

const SESION: SesionRead = {
  uuid: 'sess-uuid-1',
  uuid_sucursal: 'suc-uuid-1',
  uuid_usuario: 'usr-uuid-1',
  valor_inicial_efectivo: 100_000,
  valor_inicial_datafono: 0,
  timestamp_apertura: '2026-09-25T08:00:00Z',
  timestamp_cierre: null,
};

const baseArgs = {
  sesion: SESION,
  uuidTipoArqueo: 'tipo-arqueo-uuid-cierre-turno',
  bridge: null,
  values: {
    valor_efectivo_reportado: 100_000,
    valor_datafono_reportado: 0,
  },
};

describe('runCerrarTurnoChain — justificacion_requerida detection', () => {
  it('POST /caja/arqueo 400 justificacion_requerida → kind "justificacion_requerida", NO intenta cerrar sesión', async () => {
    const cerrarSesion = vi.fn();
    const submitArqueo = vi.fn().mockRejectedValueOnce(
      new ParkosHttpError(
        400,
        JSON.stringify({ detail: { error: 'justificacion_requerida' } }),
        '/api/v1/caja/arqueo',
      ),
    );

    const result = await runCerrarTurnoChain({
      ...baseArgs,
      submitArqueo,
      cerrarSesion,
    });

    expect(result).toEqual({ kind: 'justificacion_requerida' });
    expect(cerrarSesion).not.toHaveBeenCalled();
  });

  it('POST /caja/arqueo 400 con otro motivo → sigue cayendo a "arqueo_fallido" (no sobre-matchea)', async () => {
    const submitArqueo = vi.fn().mockRejectedValueOnce(
      new ParkosHttpError(
        400,
        JSON.stringify({ detail: { error: 'monto_invalido' } }),
        '/api/v1/caja/arqueo',
      ),
    );

    const result = await runCerrarTurnoChain({
      ...baseArgs,
      submitArqueo,
      cerrarSesion: vi.fn(),
    });

    expect(result).toEqual({ kind: 'arqueo_fallido', status: 400 });
  });

  it('POST /caja/arqueo 500 con body no-JSON → cae a "arqueo_fallido" sin romper', async () => {
    const submitArqueo = vi.fn().mockRejectedValueOnce(
      new ParkosHttpError(500, 'Internal Server Error', '/api/v1/caja/arqueo'),
    );

    const result = await runCerrarTurnoChain({
      ...baseArgs,
      submitArqueo,
      cerrarSesion: vi.fn(),
    });

    expect(result).toEqual({ kind: 'arqueo_fallido', status: 500 });
  });
});
