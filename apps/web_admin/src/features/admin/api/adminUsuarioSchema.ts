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
 * HU-F16.col rework adds:
 *   - `sucursalAsignadaResumenSchema` — lightweight branch summary
 *     embedded in `GET /admin/usuarios` (and `/{uuid}`) so the table
 *     can render chips inline without a per-row request.
 *
 * Messages are i18n KEYS so the renderer can translate via
 * `useTranslation()` at the edge — same pattern as `sucursalSchema`.
 */
import { z } from 'zod';

export const ROLES = ['admin', 'operador'] as const;
export type Rol = (typeof ROLES)[number];

/**
 * Lightweight per-branch summary embedded in :class:`AdminUsuarioRead`
 * (one element per currently-open assignment). Returned by
 * ``GET /admin/usuarios`` (list + single) so the table can render
 * branch chips inline without a per-row round-trip.
 *
 * Distinct from :class:`AdminSucursalAsignadaRead`, which carries the
 * full bi-temporal lifecycle fields (`vigente_desde`/`vigente_hasta`/
 * `estado`) for the dedicated ``GET /admin/usuarios/{uuid}/sucursales``
 * endpoint consumed by the assignment modal.
 */
export const sucursalAsignadaResumenSchema = z.object({
  uuid_sucursal: z.string().uuid(),
  nombre: z.string().nullable(),
  prefijo_nombre: z.string().nullable(),
  vigente_desde: z.string(),
});

export type SucursalAsignadaResumen = z.infer<typeof sucursalAsignadaResumenSchema>;

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
  /**
   * Currently-open branch assignments embedded by the backend on
   * ``GET /api/v1/admin/usuarios`` (and ``/{uuid}``). ``.default([])``
   * keeps the parse resilient if the backend ever omits the field —
   * the table will render "Sin sucursales" instead of crashing.
   */
  sucursales: z.array(sucursalAsignadaResumenSchema).default([]),
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
