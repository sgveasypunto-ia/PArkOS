/**
 * `cerrarTurnoChain.ts` — extracted pure helper for the F10.2 orchestrator.
 *
 * Encapsulates the 3-step sequencer that the `<CerrarTurno>` page wires
 * up via react-hook-form + Zustand:
 *   1. `POST /caja/arqueo` with `tipo_arqueo='cierre_turno'`.
 *   2. `bridge.imprimir('arqueo', { ..., auditoria_codigo: 'cierre_turno' })`
 *      (BEFORE the PUT, DA-F10.2-5 RESOLVED).
 *   3. `PUT /caja-sesion/{uuid}/cerrar` via the F3.3 logout-on-success
 *      helper (`useSesionActiva().cerrarSesion`).
 *
 * The helper returns a discriminated `CerrarTurnoChainResult` so the
 * caller (the orchestrator) can render the right banner without
 * re-implementing the precedence logic. The 8-case precedence is
 * documented at the top of `<CerrarTurno>` and codified here.
 *
 * NO retry loop. NO client-side DELETE (canon §1-§3 forbids physical
 * DELETE on `[A]` tables).
 */
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import type { SesionRead } from '../api/sesionActivaApi';

/**
 * Bridge signature: `window.bridge.imprimir(kind, payload)` per F2.2
 * DEC-FETCH-08 + `renderer/global.d.ts`. Typed as a minimal interface
 * so the helper is unit-testable without a real Electron bridge.
 */
export interface CerrarTurnoBridge {
  imprimir(kind: string, payload: Record<string, unknown>): Promise<unknown>;
}

/**
 * Helper signature for the F3.3 logout-on-success seam (REQ-OPS-160,
 * AD-4). Encapsulates `useAuthStore.clear()` + `parkos:auth:cleared`
 * event inside the result envelope.
 */
export interface CerrarSesionHelper {
  (
    uuid: string,
    payload: {
      valor_final_efectivo: number;
      valor_final_datafono: number;
      observaciones_cierre?: string;
    },
  ): Promise<
    | { ok: true; status: 200; sesion: SesionRead }
    | { ok: false; status: number; error: unknown }
  >;
}

/**
 * Arqueo submit signature for `POST /caja/arqueo` (HU-F1.13). Defined
 * here as a structural type so the helper is testable.
 */
export interface ArqueoSubmitFn {
  (payload: {
    uuid_sesion: string;
    tipo_arqueo: 'cierre_turno';
    valor_efectivo_reportado: number;
    valor_datafono_reportado: number;
    justificacion?: string;
  }): Promise<{ uuid: string }>;
}

/**
 * Result envelope returned by the chain. The orchestrator renders one
 * banner per kind + may call `navigate(...)` for the `redirect` kinds.
 */
export type CerrarTurnoChainResult =
  | { kind: 'success'; sesion: SesionRead }
  | { kind: 'redirect_login_closed' }
  | { kind: 'redirect_login' }
  | { kind: 'arqueo_fallido'; status: number }
  | { kind: 'red_arqueo' }
  | { kind: 'cierre_ya_cerrado'; uuid_arqueo?: string }
  | { kind: 'cierre_fallido'; uuid_arqueo?: string };

/**
 * Build the POST /caja/arqueo body, dropping `justificacion` when
 * empty so the wire-level body does NOT carry the field (REQ-OPS-157:
 * `|diferencia|=0` MUST NOT send a justificacion).
 */
function buildArqueoBody(args: {
  sesion: SesionRead;
  valor_efectivo_reportado: number;
  valor_datafono_reportado: number;
  justificacion?: string;
}): Parameters<ArqueoSubmitFn>[0] {
  const body: Parameters<ArqueoSubmitFn>[0] = {
    uuid_sesion: args.sesion.uuid,
    tipo_arqueo: 'cierre_turno',
    valor_efectivo_reportado: args.valor_efectivo_reportado,
    valor_datafono_reportado: args.valor_datafono_reportado,
  };
  if (args.justificacion && args.justificacion.trim() !== '') {
    body.justificacion = args.justificacion.trim();
  }
  return body;
}

/**
 * Build the PUT /caja-sesion/{uuid}/cerrar body (F3.3 contract).
 * `observaciones_cierre` is dropped when empty.
 */
function buildCerrarSesionBody(args: {
  valor_final_efectivo: number;
  valor_final_datafono: number;
  observaciones_cierre?: string;
}): Parameters<CerrarSesionHelper>[1] {
  const body: Parameters<CerrarSesionHelper>[1] = {
    valor_final_efectivo: args.valor_final_efectivo,
    valor_final_datafono: args.valor_final_datafono,
  };
  if (
    args.observaciones_cierre !== undefined &&
    args.observaciones_cierre !== ''
  ) {
    body.observaciones_cierre = args.observaciones_cierre;
  }
  return body;
}

/**
 * The 3-step sequencer (REQ-OPS-157 + AD-2 + AD-3 + AD-6).
 *
 * @param args.sesion active sesion (uuid_sesion comes from `sesion.uuid`).
 * @param args.submitArqueo `useArqueo().submit` reference.
 * @param args.cerrarSesion `useSesionActiva().cerrarSesion` reference.
 * @param args.bridge minimal `bridge.imprimir` interface.
 * @param args.values form values from `<CerrarTurnoForm>`.
 *
 * @returns a `CerrarTurnoChainResult` describing the outcome for the
 * orchestrator to map to banners + `navigate(...)`.
 */
export async function runCerrarTurnoChain(args: {
  sesion: SesionRead;
  submitArqueo: ArqueoSubmitFn;
  cerrarSesion: CerrarSesionHelper;
  bridge: CerrarTurnoBridge | null;
  values: {
    valor_efectivo_reportado: number;
    valor_datafono_reportado: number;
    justificacion?: string;
    valor_final_efectivo: number;
    valor_final_datafono: number;
    observaciones_cierre?: string;
  };
}): Promise<CerrarTurnoChainResult> {
  // 1. POST /caja/arqueo FIRST (REQ-OPS-157). On ANY error here we
  // ABORT — no PUT call, no bridge.imprimir.
  let arqueoUuid: string | undefined;
  try {
    const arqueoResult = await args.submitArqueo(
      buildArqueoBody({
        sesion: args.sesion,
        valor_efectivo_reportado: args.values.valor_efectivo_reportado,
        valor_datafono_reportado: args.values.valor_datafono_reportado,
        justificacion: args.values.justificacion,
      }),
    );
    arqueoUuid = arqueoResult.uuid;

    // 2. ESC/POS print (BEFORE the PUT). DA-F10.2-5 RESOLVED — the
    // dispatcher accepts `auditoria_codigo='cierre_turno'` without
    // escpos changes (F10.1 `'arqueo'` union extension).
    if (args.bridge !== null) {
      await args.bridge.imprimir('arqueo', {
        ...arqueoResult,
        auditoria_codigo: 'cierre_turno',
      });
    }
  } catch (err) {
    // Cases 1-4: POST errors. NO sesion close attempted.
    if (err instanceof TypeError) {
      return { kind: 'red_arqueo' };
    }
    const status =
      err instanceof ParkosHttpError ? err.status : 0;
    return { kind: 'arqueo_fallido', status };
  }

  // 3. PUT /caja-sesion/{uuid}/cerrar via the F3.3 logout-on-success
  // helper. The helper owns the F3.3 logout-on-success trifecta
  // (`useAuthStore.clear()` + `parkos:auth:cleared` event) per
  // REQ-OPS-160 + AD-4. The orchestrator only has to `navigate` on
  // `ok: true`.
  const result = await args.cerrarSesion(
    args.sesion.uuid,
    buildCerrarSesionBody({
      valor_final_efectivo: args.values.valor_final_efectivo,
      valor_final_datafono: args.values.valor_final_datafono,
      observaciones_cierre: args.values.observaciones_cierre,
    }),
  );

  if (result.ok) {
    return { kind: 'redirect_login_closed', sesion: result.sesion };
  }

  // Cases 5-8: PUT errors. The helper did NOT clear (except 401,
  // which is handled inside the helper per AD-4 — see the helper
  // tests in `hooks/__tests__/useSesionActiva.cerrarSesion.test.ts`).
  if (result.status === 404) {
    // Case 5: SesionAlreadyClosedError (404) → navigate /login,
    // no ?closed=true (DEC-F3.3-07).
    return { kind: 'redirect_login' };
  }
  if (result.status === 401) {
    // Case 8: 401 → F3.3 fallback handled inside helper. Operator
    // is already cleared; orchestrator only navigates.
    return { kind: 'redirect_login' };
  }
  // Cases 6-7: 409 / 5xx / network. Surface orphan uuid banner.
  // ABBC-F10.2-BE-1 (pending-fase-10.md item #4) is the future
  // automated reconciler — interim remediation is operator-driven
  // with the surfaced uuid.
  return {
    kind: result.status === 409 ? 'cierre_ya_cerrado' : 'cierre_fallido',
    uuid_arqueo: arqueoUuid,
  };
}