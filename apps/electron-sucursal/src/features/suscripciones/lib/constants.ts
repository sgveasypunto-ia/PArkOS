/**
 * `lib/constants.ts` — feature-wide constants for the `suscripciones`
 * capability. Single source of truth for tunables that need to be
 * referenced from both the hook layer (`hooks/useSuscripcionesProximasVencer.ts`)
 * and the UI layer (`pages/Listado.tsx`, `<Dashboard />` banner).
 *
 * REQ-OPS-184 (HU-F9.2 ABIERTO-05 drift anchor) — the
 * `dias_alerta_pre_vencimiento` threshold is GLOBAL only. There is
 * NO per-suscripción override on this branch; that capability
 * (CU-06 BR4) is wired as the explicit follow-up "ABIERTO-05". The
 * `git grep dias_alerta_pre_vencimiento_override` AST drift guard
 * depends on this constant being the canonical reference.
 */
export const DEFAULT_DIAS_ALERTA_PRE_VENCIMIENTO = 7;
