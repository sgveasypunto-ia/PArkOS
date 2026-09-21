/**
 * `types.ts` — TS types re-exported from the FE Zod schemas for the
 * `features/alertas/` subtree (HU-F11.2, REQ-OPS-177).
 *
 * Keeping a single re-export barrel avoids the duplicate-import
 * pattern (`@/lib/api/schemas/alertas` vs `@/features/alertas/types`)
 * that bit F11.1 — consumers import from `@/features/alertas/types`
 * for the row shape and `@/lib/api/schemas/alertas` for the parser
 * primitives (Zod schemas live in the lib tree per `lib/`
 * organization convention; the type-only mirror keeps cycle risk
 * low).
 */
export type {
  AlertaRead,
  AlertTypeRead,
  MergedAlerta,
  AlertaEstado,
} from '../../lib/api/schemas/alertas';

export {
  ALERTA_ESTADO,
  AlertaSchema,
  AlertaReadListSchema,
  AlertTypeSchema,
  AlertTypeReadListSchema,
} from '../../lib/api/schemas/alertas';
