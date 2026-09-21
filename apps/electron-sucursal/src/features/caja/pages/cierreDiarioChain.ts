/**
 * `cierreDiarioChain.ts` — pure helper for the F10.3 Cierre Diario
 * orchestrator (REQ-OPS-166, AD-2).
 *
 * 2-step sequencer that mirrors F10.2 `cerrarTurnoChain.ts` but
 * FLATTENED to POST + bridge.imprimir because the backend
 * `cerrar_sesiones_del_dia_bulk` (KD-ARQUEO-03, triggered at
 * `caja_arqueo.py:266-272`) handles per-session closure in-tx.
 *
 * The helper is import-pure (no React hooks, no module-level side
 * effects) so the unit tests in
 * `pages/__tests__/cierreDiarioChain.test.ts` can exercise every
 * result kind with a mocked `submitArqueo` and `bridge`.
 *
 * Discriminated `CierreDiarioChainResult` envelope (5 kinds per
 * REQ-OPS-166):
 *   - 'success' — happy 2-step; bridge.imprimir rejection is non-fatal.
 *   - 'arqueo_fallido' — POST 4xx/5xx (ParkosHttpError); the bridge
 *     is NOT called.
 *   - 'red_arqueo' — POST TypeError (network); the bridge is NOT called.
 *   - 'ya_cerrado' — POST 409 cierre_dia already exists (defensive).
 *   - 'permiso_insuficiente' — POST 403 tenant_scope_violation.
 *
 * Drift anchors resolved:
 *   - DA-F10.3-1 — backend `cerrar_sesiones_del_dia_bulk` is
 *     single-commit; FE assumes all-or-nothing success.
 *   - DA-F10.3-6 — escpos `auditoria_codigo='cierre_dia'` flows
 *     through unchanged from F10.2 (no escpos changes).
 *   - DA-F10.3-7 — `useCierreDiario()` legacy remains bit-identical
 *     (deprecation marker only).
 *
 * NO retry loop. NO client-side DELETE on `[A]` tables (canon §1-§3
 * forbids physical DELETE on append-only arqueo rows).
 */
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

/**
 * Bridge signature: `window.bridge.imprimir(kind, payload)` per F2.2
 * DEC-FETCH-08 + `renderer/global.d.ts`. Typed as a minimal interface
 * so the helper is unit-testable without a real Electron bridge.
 */
export interface CierreDiarioBridge {
  imprimir(kind: string, payload: Record<string, unknown>): Promise<unknown>;
}

/**
 * `ArqueoSubmitFn` — structural type for `useArqueo().submit` shape.
 * The `uuid_sesion` literal type is `null` (NOT `string`) — this is
 * the corrigendum for the buggy `useCierreDiario()` helper at
 * `useArqueo.ts:107-117` that incorrectly typed it as `string`.
 */
export interface ArqueoSubmitFn {
  (payload: {
    uuid_sesion: null;
    tipo_arqueo: 'cierre_dia';
    valor_efectivo_reportado: number;
    valor_datafono_reportado: number;
    justificacion?: string;
  }): Promise<{ uuid: string }>;
}

/**
 * Discriminated result envelope returned by the chain. The
 * orchestrator (the `<CierreDiario />` page) maps each kind to a
 * banner + (on success) a `navigate('/')` call. The supervisor flow
 * preserves the JWT (NO `useAuthStore.clear()`) — see AD-3.
 */
export type CierreDiarioChainResult =
  | { kind: 'success'; uuid_arqueo: string }
  | { kind: 'arqueo_fallido'; status: number }
  | { kind: 'red_arqueo' }
  | { kind: 'ya_cerrado'; uuid_arqueo?: string }
  | { kind: 'permiso_insuficiente'; status: number };

/**
 * Build the POST /caja/arqueo body, dropping `justificacion` when
 * empty so the wire-level body does NOT carry the field (mirrors
 * F10.2 `buildArqueoBody` at `cerrarTurnoChain.ts:84-100`).
 */
function buildArqueoBody(values: {
  valor_efectivo_reportado: number;
  valor_datafono_reportado: number;
  justificacion?: string;
}): Parameters<ArqueoSubmitFn>[0] {
  const body: Parameters<ArqueoSubmitFn>[0] = {
    uuid_sesion: null,
    tipo_arqueo: 'cierre_dia',
    valor_efectivo_reportado: values.valor_efectivo_reportado,
    valor_datafono_reportado: values.valor_datafono_reportado,
  };
  if (values.justificacion && values.justificacion.trim() !== '') {
    body.justificacion = values.justificacion.trim();
  }
  return body;
}

/**
 * The 2-step sequencer (REQ-OPS-166, AD-2).
 *
 * @param args.submitArqueo `useArqueo().submit` reference (typed
 *        via `ArqueoSubmitFn`).
 * @param args.bridge minimal `bridge.imprimir` interface (or null in
 *        test environment where the bridge is not wired).
 * @param args.values form values from `<CierreDiarioForm />`.
 *
 * @returns a `CierreDiarioChainResult` describing the outcome for
 * the orchestrator to map to banners + `navigate('/')`.
 */
export async function runCierreDiarioChain(args: {
  submitArqueo: ArqueoSubmitFn;
  bridge: CierreDiarioBridge | null;
  values: {
    valor_efectivo_reportado: number;
    valor_datafono_reportado: number;
    justificacion?: string;
  };
}): Promise<CierreDiarioChainResult> {
  // Step 1: POST /caja/arqueo with cierre_dia discriminator. On ANY
  // error here we ABORT — no bridge.imprimir, no retry, no fallback.
  let arqueoUuid: string | undefined;
  try {
    const arqueoResult = await args.submitArqueo(
      buildArqueoBody(args.values),
    );
    arqueoUuid = arqueoResult.uuid;

    // Step 2: ESC/POS print. DA-F10.3-6 RESOLVED — the bridge
    // failure is logged but non-fatal (F10.2 precedent).
    if (args.bridge !== null) {
      try {
        await args.bridge.imprimir('arqueo', {
          ...arqueoResult,
          auditoria_codigo: 'cierre_dia',
        });
      } catch (err) {
        // BORDER tolerant — F10.2 DA-F10.2-5 RESOLVED. We log
        // observability so the supervisor can investigate post-hoc
        // without aborting the success path.
        console.warn(
          'escpos_printer_offline',
          err instanceof Error ? err.message : String(err),
        );
      }
    }

    return { kind: 'success', uuid_arqueo: arqueoResult.uuid };
  } catch (err) {
    // Cases 1-4: POST errors. NO bridge.imprimir, NO retry.
    if (err instanceof TypeError) {
      return { kind: 'red_arqueo' };
    }
    const status = err instanceof ParkosHttpError ? err.status : 0;
    if (status === 409) {
      return { kind: 'ya_cerrado', uuid_arqueo: arqueoUuid };
    }
    if (status === 403) {
      return { kind: 'permiso_insuficiente', status };
    }
    return { kind: 'arqueo_fallido', status };
  }
}