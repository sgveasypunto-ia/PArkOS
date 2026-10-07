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
 * The `uuid_sesion` literal type is `null` (cierre_dia has no sesion).
 *
 * The BE V2 schema (`ArqueoCreateV2`, `extra='forbid'`) requires
 * `uuid_tipo_arqueo` (UUID FK to `prod.tipo_arqueo`) and rejects the legacy
 * `tipo_arqueo` codigo string with a 422. The caller resolves `'cierre_dia'`
 * to its UUID via `useTipoArqueoPorCodigo`.
 */
export interface ArqueoSubmitFn {
  (payload: {
    uuid_sesion: null;
    uuid_tipo_arqueo: string;
    valor_efectivo_reportado: number;
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
  | { kind: 'arqueo_fallido'; status: number; detail?: string }
  | { kind: 'red_arqueo' }
  | { kind: 'ya_cerrado'; uuid_arqueo?: string }
  | { kind: 'permiso_insuficiente'; status: number };

/**
 * Turn the raw body of a `ParkosHttpError` into a short, human-readable
 * server detail so the page can show WHY the close failed instead of a
 * generic banner. Handles the two backend shapes:
 *   - `{"detail":{"error":"justificacion_requerida"}}` → the error code;
 *   - FastAPI 422 `{"detail":[{"loc":[...],"msg":"..."}]}` → `loc: msg` joined.
 * `undefined` when the body is not JSON or carries neither shape.
 */
function parseServerDetail(body: string): string | undefined {
  let parsed: unknown;
  try {
    parsed = JSON.parse(body);
  } catch {
    return undefined;
  }
  const detail = (parsed as { detail?: unknown } | null)?.detail;
  if (typeof detail === 'string' && detail !== '') return detail;
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        const { loc, msg } = (item ?? {}) as { loc?: unknown; msg?: unknown };
        if (typeof msg !== 'string') return undefined;
        const where = Array.isArray(loc) ? loc.join('.') : '';
        return where !== '' ? `${where}: ${msg}` : msg;
      })
      .filter((x): x is string => x !== undefined);
    return parts.length > 0 ? parts.join('; ') : undefined;
  }
  const code = (detail as { error?: unknown } | null | undefined)?.error;
  return typeof code === 'string' && code !== '' ? code : undefined;
}

/**
 * Build the POST /caja/arqueo body, dropping `justificacion` when
 * empty so the wire-level body does NOT carry the field (mirrors
 * F10.2 `buildArqueoBody` at `cerrarTurnoChain.ts:84-100`).
 */
function buildArqueoBody(
  uuidTipoArqueo: string,
  values: {
    valor_efectivo_reportado: number;
    justificacion?: string;
  },
): Parameters<ArqueoSubmitFn>[0] {
  const body: Parameters<ArqueoSubmitFn>[0] = {
    uuid_sesion: null,
    uuid_tipo_arqueo: uuidTipoArqueo,
    valor_efectivo_reportado: values.valor_efectivo_reportado,
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
 * @param args.uuidTipoArqueo resolved UUID of the `cierre_dia` tipo_arqueo.
 * @param args.bridge minimal `bridge.imprimir` interface (or null in
 *        test environment where the bridge is not wired).
 * @param args.values form values from `<CierreDiarioForm />`.
 *
 * @returns a `CierreDiarioChainResult` describing the outcome for
 * the orchestrator to map to banners + `navigate('/')`.
 */
export async function runCierreDiarioChain(args: {
  submitArqueo: ArqueoSubmitFn;
  /** UUID of the `cierre_dia` row in `prod.tipo_arqueo` (catalog lookup). */
  uuidTipoArqueo: string;
  bridge: CierreDiarioBridge | null;
  values: {
    valor_efectivo_reportado: number;
    justificacion?: string;
  };
}): Promise<CierreDiarioChainResult> {
  // Step 1: POST /caja/arqueo with cierre_dia discriminator. On ANY
  // error here we ABORT — no bridge.imprimir, no retry, no fallback.
  let arqueoUuid: string | undefined;
  try {
    const arqueoResult = await args.submitArqueo(
      buildArqueoBody(args.uuidTipoArqueo, args.values),
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
    const detail =
      err instanceof ParkosHttpError ? parseServerDetail(err.body) : undefined;
    return detail !== undefined
      ? { kind: 'arqueo_fallido', status, detail }
      : { kind: 'arqueo_fallido', status };
  }
}