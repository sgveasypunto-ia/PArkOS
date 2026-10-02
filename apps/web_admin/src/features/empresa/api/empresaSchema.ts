/**
 * `empresaSchema.ts` — Zod schemas + types for the admin Empresa UI
 * (HU-F15.2 of `plan.md:3537`).
 *
 * Mirrors the backend `schemas/empresa.py::EmpresaRead` /
 * `EmpresaUpdate` exactly so a round-trip parse never fails on a
 * fresh payload.
 *
 * The backend already exposes:
 *   - `GET  /api/v1/empresa/empresa`          (list; singleton returns 1 row)
 *   - `POST /api/v1/empresa/empresa`          (create)
 *   - `PUT  /api/v1/empresa/empresa/{uuid}`   (update; bi-temporal close+insert)
 *
 * so this file is THIN -- just the zod shape + TS types the UI needs.
 * No HTTP client lives here; that lives in `empresaApi.ts`.
 */
import { z } from 'zod';

export const regimenSchema = z.enum(['comun', 'simplificado']);
export type Regimen = z.infer<typeof regimenSchema>;

export const empresaUpdateSchema = z.object({
  nombre: z
    .string()
    .min(1, 'El nombre es obligatorio')
    .max(255, 'La razón social no puede superar los 255 caracteres'),
  nit: z
    .string()
    .min(6, 'El NIT es obligatorio (mínimo cuerpo + DV)')
    .max(32, 'El NIT no puede superar los 32 caracteres'),
  regimen: regimenSchema,
});
export type EmpresaUpdateInput = z.infer<typeof empresaUpdateSchema>;

export const empresaMensajesUpdateSchema = z.object({
  mensaje_bienvenida: z
    .string()
    .max(2000, 'El mensaje no puede superar los 2000 caracteres')
    .nullable(),
  mensaje_salida: z
    .string()
    .max(2000, 'El mensaje no puede superar los 2000 caracteres')
    .nullable(),
});
export type EmpresaMensajesUpdateInput = z.infer<typeof empresaMensajesUpdateSchema>;

export const empresaReadSchema = z.object({
  uuid: z.string().uuid(),
  nombre: z.string().nullable(),
  nit: z.string().nullable(),
  mensaje_bienvenida: z.string().nullable(),
  mensaje_salida: z.string().nullable(),
  regimen: z.string().nullable(),
  vigente_desde: z.string(),
  vigente_hasta: z.string().nullable(),
  estado: z.string(),
  created_at: z.string(),
  created_by: z.string().uuid().nullable(),
  sync_status: z.string().nullable(),
});
export type Empresa = z.infer<typeof empresaReadSchema>;

export const empresaReadListSchema = z.object({
  items: z.array(empresaReadSchema),
  next_cursor: z.string().nullable(),
});
