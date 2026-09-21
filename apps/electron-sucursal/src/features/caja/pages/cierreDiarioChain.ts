/**
 * Stub for the RED scaffold (HU-F10.3 — Commit 1). The GREEN
 * implementation lands in Commit 2.
 *
 * The stub throws a sentinel "not implemented" error so any test
 * that accidentally executes the body (instead of the import-only
 * contract check) fails loudly. Once C2 lands, this stub is
 * replaced by the real 2-step sequencer that mirrors F10.2's
 * `cerrarTurnoChain.ts` but flattened to POST + bridge.imprimir
 * (NO PUT sesion-close; backend `cerrar_sesiones_del_dia_bulk`
 * handles mass-close in-tx).
 *
 * Drift anchors resolved by the GREEN impl:
 *   - DA-F10.3-6 — escpos `auditoria_codigo='cierre_dia'` flows
 *     through unchanged from F10.2.
 *   - DA-F10.3-7 — `useCierreDiario()` legacy remains bit-identical
 *     (deprecation marker only).
 */
export type CierreDiarioChainResult = never;

export interface CierreDiarioBridge {
  imprimir(kind: string, payload: Record<string, unknown>): Promise<unknown>;
}

export interface ArqueoSubmitFn {
  (payload: {
    uuid_sesion: null;
    tipo_arqueo: 'cierre_dia';
    valor_efectivo_reportado: number;
    valor_datafono_reportado: number;
    justificacion?: string;
  }): Promise<{ uuid: string }>;
}

export function runCierreDiarioChain(_args: {
  submitArqueo: ArqueoSubmitFn;
  bridge: CierreDiarioBridge | null;
  values: {
    valor_efectivo_reportado: number;
    valor_datafono_reportado: number;
    justificacion?: string;
  };
}): Promise<CierreDiarioChainResult> {
  throw new Error('runCierreDiarioChain: not implemented (RED scaffold)');
}