/**
 * `sucursalSchema.ts` — Zod schemas for the admin Sucursal CRUD UI
 * (IT-2.1, IT-2.7 of `openspec/_meta/iteration-plan.md`).
 *
 * Mirrors the backend `schemas/empresa.py::SucursalCreate` /
 * `SucursalRead` shape, plus the read-side payload needed by the
 * PairingTokenDialog.
 *
 * The backend already exposes:
 *   - `GET  /api/v1/empresa/sucursal`         (list, paginated)
 *   - `POST /api/v1/empresa/sucursal`         (create, admin only)
 *   - `PUT  /api/v1/empresa/sucursal/{uuid}`  (update, admin only)
 *   - `GET  /api/v1/sucursal/{uuid}/pairing-token` (admin only,
 *     24h single-use)
 *
 * so this file is THIN -- just the zod shape + TS types the UI needs.
 * No HTTP client lives here; that lives in `sucursalesApi.ts`.
 */
import { z } from 'zod';

export const sucursalCreateSchema = z.object({
  nombre: z.string().min(1, 'El nombre es obligatorio').max(255),
  direccion: z.string().max(255).nullish(),
  telefono: z.string().max(64).nullish(),
  prefijo_nombre: z
    .string()
    .min(1, 'El prefijo es obligatorio (UK)')
    .max(64)
    // 3-7 chars: the production seed uses "BOG-CEN" / "MED-NOR" (7 chars
    // including the dash). Uppercase letters + digits + dash.
    .regex(/^[A-Z0-9-]{3,7}$/, 'Prefijo: 3-7 caracteres en mayusculas, digitos o guion'),
  ciudad: z.string().max(255).nullish(),
  horario: z.string().max(255).nullish(),
  uuid_tipo_sucursal: z.string().uuid().nullish(),
  uuid_empresa: z.string().uuid().nullish(),
});

export type SucursalCreateInput = z.infer<typeof sucursalCreateSchema>;

// Mirror of the create schema: `SucursalUpdate` is "same shape as Create"
// per backend `schemas/empresa.py::SucursalUpdate`. The Create rule on
// `prefijo_nombre` is duplicated here so the standalone-update form
// validates the same way without depending on Create.
export const sucursalUpdateSchema = z.object({
  nombre: z.string().min(1, 'El nombre es obligatorio').max(255),
  direccion: z.string().max(255).nullish(),
  telefono: z.string().max(64).nullish(),
  prefijo_nombre: z
    .string()
    .min(1, 'El prefijo es obligatorio (UK)')
    .max(64)
    .regex(/^[A-Z0-9-]{3,7}$/, 'Prefijo: 3-7 caracteres en mayusculas, digitos o guion'),
  ciudad: z.string().max(255).nullish(),
  horario: z.string().max(255).nullish(),
  uuid_tipo_sucursal: z.string().uuid().nullish(),
  uuid_empresa: z.string().uuid().nullish(),
});

export type SucursalUpdateInput = z.infer<typeof sucursalUpdateSchema>;

export const sucursalReadSchema = z.object({
  uuid: z.string().uuid(),
  nombre: z.string().nullable(),
  direccion: z.string().nullable(),
  telefono: z.string().nullable(),
  prefijo_nombre: z.string().nullable(),
  ciudad: z.string().nullable(),
  horario: z.string().nullable(),
  uuid_tipo_sucursal: z.string().uuid().nullable(),
  uuid_empresa: z.string().uuid().nullable(),
  vigente_desde: z.string(),
  vigente_hasta: z.string().nullable(),
  estado: z.string(),
  created_at: z.string(),
  created_by: z.string().uuid().nullable(),
  sync_status: z.string().nullable(),
});

export type Sucursal = z.infer<typeof sucursalReadSchema>;

export const sucursalReadListSchema = z.object({
  items: z.array(sucursalReadSchema),
  next_cursor: z.string().nullable(),
});

export const pairingTokenResponseSchema = z.object({
  token: z.string().min(1),
  expires_at: z.string(),
  sucursal_uuid: z.string().uuid(),
});

export type PairingTokenResponse = z.infer<typeof pairingTokenResponseSchema>;
