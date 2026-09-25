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
 * BUGFIX (2026-09-25, directiva del operador): esta capa describía un
 * contrato que el backend nunca implementó — `POST .../{uuid}/reimprimir`
 * con body `{motivo, tipo}` no existe. El endpoint real es
 * `backend/.../api/v1/workflows_reimpresion.py::create_reimpresion_ticket`:
 *
 *   - `POST /api/v1/workflows/reimpresion-ticket` (ruta RAÍZ, sin
 *     sufijo) body `ReimpresionTicketCreateEndpoint` = `{uuid_ingreso,
 *     motivo: string(10..500), uuid_factura?}` → 201
 *     `ReimpresionTicketRead`. `tipo` NUNCA se envía al backend — es un
 *     detalle puramente de impresión (qué variante de
 *     `escposBuilder.build('reimpresion', payload)` armar), no del wire
 *     contract.
 *   - `POST /api/v1/workflows/reimpresion-ticket/{uuid}/anular` body
 *     `{motivo_anulacion: string(10..500)}` → 201 con fila nueva
 *     (`uuid_reimpresion_padre=<original>`; NEVER UPDATE en `[L-W]`).
 *
 * Verificado contra `schemas/workflows.py::ReimpresionTicketRead` +
 * `ReimpresionTicketCreateEndpoint` y los handlers reales — el enum de
 * `workflow_estado` es exactamente `'autorizada' | 'rechazada'`
 * (los otros dos literales que este archivo declaraba antes,
 * `'solicitada'`/`'ejecutada'`, no existen en el backend). Se agrega
 * `costo_aplicado` (faltaba) — es el snapshot de `costos_servicios`
 * que el backend cobra y que la UI necesita mostrar/imprimir.
 */
import { z } from 'zod';

/**
 * F8.3 — create-input schema, espejo EXACTO de
 * `ReimpresionTicketCreateEndpoint` (backend). `motivo` acepta 10..500
 * caracteres (`StringConstraints` del backend); `uuid_factura` es
 * opcional (DEC-TKT-04).
 */
export const ReimpresionTicketCreateSchema = z.object({
  uuid_ingreso: z.string().uuid(),
  motivo: z
    .string()
    .min(10, 'motivo_muy_corto')
    .max(500, 'motivo_muy_largo'),
  uuid_factura: z.string().uuid().optional(),
});
export type ReimpresionTicketCreate = z.infer<typeof ReimpresionTicketCreateSchema>;

/**
 * F8.3 — anulación input schema (mirror F1.11 REQ-OPS-077).
 * Same `min(10)` constraint as create — symmetry is the principle
 * of least surprise (proposal OD-2 ratified).
 */
export const ReimpresionTicketAnularSchema = z.object({
  motivo_anulacion: z.string().min(10, 'motivo_anulacion_muy_corto').max(500, 'motivo_anulacion_muy_largo'),
});
export type ReimpresionTicketAnular = z.infer<typeof ReimpresionTicketAnularSchema>;

/**
 * F8.3 — read shape (mirror F1.11 `ReimpresionTicketRead`):
 *   - `workflow_estado` — `'autorizada'` on create, `'rechazada'` on
 *     anulación (F1.11 DEC-TKT-03). The backend ALWAYS sets it
 *     explicitly on both handlers — never `null` on the wire.
 *   - `costo_aplicado` — snapshot of `costos_servicios.costo` at
 *     charge time (Decimal on the backend; FastAPI serializes it as a
 *     JSON number, but `z.coerce.number()` tolerates either shape).
 *   - `uuid_reimpresion_padre` nullable — null on root, populated on
 *     every chain continuation.
 *   - `uuid_factura` nullable — DEC-TKT-04 OPTIONAL.
 */
export const ReimpresionTicketReadSchema = z.object({
  uuid: z.string().uuid(),
  workflow_estado: z.enum(['autorizada', 'rechazada']),
  uuid_reimpresion_padre: z.string().uuid().nullable(),
  uuid_ingreso: z.string().uuid(),
  uuid_factura: z.string().uuid().nullable(),
  costo_aplicado: z.coerce.number().nullable(),
  motivo: z.string(),
  motivo_anulacion: z.string().nullable().optional(),
  created_at: z.string(),
});
export type ReimpresionTicketRead = z.infer<typeof ReimpresionTicketReadSchema>;
