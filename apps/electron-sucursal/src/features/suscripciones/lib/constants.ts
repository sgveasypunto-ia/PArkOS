/**
 * `lib/constants.ts` — feature-wide constants for the `suscripciones`
 * capability. Single source of truth for tunables that need to be
 * referenced from both the hook layer (`hooks/useSuscripcionesProximasVencer.ts`)
 * and the UI layer (`pages/Listado.tsx`, `<Dashboard />` banner).
 *
 * REQ-OPS-184 (HU-F9.2 ABIERTO-05 drift anchor) — the
 * `dias_alerta_pre_vencimiento` threshold is GLOBAL only. There is
 * NO per-suscripción override capability on this branch; that
 * follow-up (CU-06 BR4, "ABIERTO-05") remains closed. The drift
 * guard is enforced at the orchestration layer (`sdd-apply`
 * pre-commit verification) via the AST grep for any
 * per-suscripción override field that would contravene this
 * convention.
 */
export const DEFAULT_DIAS_ALERTA_PRE_VENCIMIENTO = 7;
