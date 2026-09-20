/**
 * `reimpresionApi.ts` — Zod mirror of the F1.11 `ReimpresionTicket`
 * wire shapes (HU-F8.3, REQ-OPS-173 + REQ-OPS-174).
 *
 * Mirrors `features/facturacion/api/facturaApi.ts` (F8.1) precedent:
 * the renderer-side Zod parser enforces the wire contract + nested
 * invariants so a misbehaving backend (extra fields, wrong types,
 * missing motivo) surfaces as a parse error instead of silently
 * rendering a half-truthy reimpresion.
 *
 * Wire contract (F1.11 REQ-OPS-075 + REQ-OPS-080 + DEC-TKT-04):
 *   - `POST /api/v1/workflows/reimpresion-ticket/{uuid_ingreso}/reimprimir`
 *     body `{motivo: string(min 10), tipo: 'entrada' | 'salida'}` →
 *     201 `ReimpresionTicketRead`.
 *   - `POST /api/v1/workflows/reimpresion-ticket/{uuid}/anular`
 *     body `{motivo_anulacion: string(min 10)}` → 201 with new row
 *     (uuid_reimpresion_padre=<original>; NEVER UPDATE on `[L-W]`).
 *
 * The `uuid_factura` field on the read shape is OPTIONAL (DEC-TKT-04)
 * — F8.3 single-step POST consumes the F1.11 endpoint directly
 * without first creating a `prod.facturas` row. The admin-correction
 * use case (anular a reimpresion with charging typo) is served by
 * leaving `uuid_factura` nullable.
 */
import { z } from 'zod';

/**
 * F8.3 — create-input schema. `motivo: min(10)` is the F1.11
 * StringConstraint (migration 0001 line 1638-1692). The hook MUST
 * pre-validate against this schema BEFORE the POST so the operator
 * never sees a 400 round-trip for motivo_muy_corto.
 */
export const ReimpresionTicketCreateSchema = z.object({
  motivo: z.string().min(10, 'motivo_muy_corto'),
  tipo: z.enum(['entrada', 'salida']),
});
export type ReimpresionTicketCreate = z.infer<typeof ReimpresionTicketCreateSchema>;

/**
 * F8.3 — anulación input schema (mirror F1.11 REQ-OPS-077).
 * Same `min(10)` constraint as create — symmetry is the principle
 * of least surprise (proposal OD-2 ratified).
 */
export const ReimpresionTicketAnularSchema = z.object({
  motivo_anulacion: z.string().min(10, 'motivo_anulacion_muy_corto'),
});
export type ReimpresionTicketAnular = z.infer<typeof ReimpresionTicketAnularSchema>;

/**
 * F8.3 — read shape (mirror F1.11 `ReimpresionTicketRead`):
 *   - `workflow_estado` discriminator — `'autorizada'` on create,
 *     `'rechazada'` on anulación (F1.11 DEC-TKT-03).
 *   - `uuid_reimpresion_padre` nullable — null on root, populated on
 *     every chain continuation.
 *   - `uuid_factura` nullable — DEC-TKT-04 OPTIONAL.
 */
export const ReimpresionTicketReadSchema = z.object({
  uuid: z.string().uuid(),
  workflow_estado: z.enum(['autorizada', 'rechazada', 'solicitada', 'ejecutada']),
  uuid_reimpresion_padre: z.string().uuid().nullable(),
  uuid_ingreso: z.string().uuid(),
  uuid_factura: z.string().uuid().nullable(),
  motivo: z.string(),
  motivo_anulacion: z.string().nullable().optional(),
  created_at: z.string(),
});
export type ReimpresionTicketRead = z.infer<typeof ReimpresionTicketReadSchema>;
