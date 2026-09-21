/**
 * Stub for the RED scaffold (HU-F10.3 — Commit 1). The GREEN
 * implementation lands in Commit 2.
 *
 * Will throw a sentinel "not implemented" error if any test path
 * accidentally reaches this stub; the RED scaffold tests assert
 * the exported function exists and types correctly without
 * exercising the body. Once C2 lands, this stub is replaced by
 * the real SWR hook.
 *
 * Drift anchors resolved by the GREEN impl:
 *   - DA-F10.3-4 — per-session shape from F1.13 backend
 *     ArqueoResumenRead (NOT the F10.1 aggregate, which is drifted).
 *   - NEW-DA-F10.3-9 — legacy useArqueoResumen Zod drift is left
 *     intact; this hook ships the corrected `.strict()` schema.
 */
export function useArqueoResumenPorSesion(
  _uuid_sucursal: string | null,
  _fecha: string | null,
): {
  data: undefined;
  refresh: () => Promise<undefined>;
} {
  throw new Error('useArqueoResumenPorSesion: not implemented (RED scaffold)');
}