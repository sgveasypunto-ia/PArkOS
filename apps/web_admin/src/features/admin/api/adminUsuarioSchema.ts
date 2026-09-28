/**
 * `adminUsuarioSchema.ts` — Zod schemas for the admin user-management
 * surface (IT-1.4 + PR3 of the web_admin redesign).
 *
 * Wire shape mirrors the backend
 * `schemas/admin.py::AdminUsuarioCreateRequest`:
 *   - `email` (required, RFC valid via `ParkosEmail` on the backend).
 *   - `password` plaintext at the edge (bcrypt on the server).
 *   - `rol` (`admin` | `operador`).
 *   - `sucursales_asignadas` — list of UUIDs the user can manage; empty
 *     list means "create the user without branch assignment". The
 *     admin can attach branches later via
 *     `POST /admin/usuarios/{uuid}/sucursales`.
 *
 * PR3 adds:
 *   - `adminUsuarioReadListSchema` — envelope for `GET /admin/usuarios`.
 *   - `adminSucursalAsignadaReadSchema` — single assignment row from
 *     `GET/POST /admin/usuarios/{uuid}/sucursales`.
 *
 * Messages are i18n KEYS so the renderer can translate via
 * `useTranslation()` at the edge — same pattern as `sucursalSchema`.
 */
import { z } from 'zod';

export const ROLES = ['admin', 'operador'] as const;
export type Rol = (typeof ROLES)[number];

export const adminUsuarioCreateSchema = z.object({
  email: z.string().min(1, 'validation.required').email('validation.email.invalid'),
  password: z
    .string()
    .min(8, 'validation.password.minLength')
    .max(128, 'validation.password.maxLength'),
  rol: z.enum(ROLES, {
    errorMap: () => ({ message: 'validation.rol.invalid' }),
  }),
  nombre: z.string().max(255).nullish(),
  apellido: z.string().max(255).nullish(),
  cedula: z.string().max(64).nullish(),
  sucursales_asignadas: z.array(z.string().uuid()).default([]),
});

export type AdminUsuarioCreateInput = z.infer<typeof adminUsuarioCreateSchema>;

export const adminUsuarioReadSchema = z.object({
  uuid: z.string().uuid(),
  email: z.string().nullable(),
  nombre: z.string().nullable(),
  apellido: z.string().nullable(),
  cedula: z.string().nullable(),
  rol: z.string().nullable(),
  vigente_desde: z.string(),
  vigente_hasta: z.string().nullable(),
  estado: z.string(),
  created_at: z.string(),
  created_by: z.string().uuid().nullable(),
  sync_status: z.string().nullable(),
});

export type AdminUsuarioRead = z.infer<typeof adminUsuarioReadSchema>;

export const adminUsuarioReadListSchema = z.object({
  items: z.array(adminUsuarioReadSchema),
  next_cursor: z.string().nullable().optional(),
});

export type AdminUsuarioReadList = z.infer<typeof adminUsuarioReadListSchema>;

/**
 * A single open branch assignment. Backend returns at minimum the
 * `uuid_sucursal` (FK). The optional `nombre` is filled by the
 * frontend from the cached `/api/v1/empresa/sucursal` directory.
 */
export const adminSucursalAsignadaReadSchema = z.object({
  uuid: z.string().uuid().optional(),
  uuid_sucursal: z.string().uuid(),
  vigente_desde: z.string().optional(),
  vigente_hasta: z.string().nullable().optional(),
  estado: z.string().optional(),
  nombre: z.string().nullable().optional(),
});

export type AdminSucursalAsignadaRead = z.infer<typeof adminSucursalAsignadaReadSchema>;
