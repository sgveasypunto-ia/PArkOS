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
  email: z
    .string()
    .min(1, 'Este campo es obligatorio.')
    .email('Ingresá un correo electrónico válido.'),
  password: z
    .string()
    .min(8, 'La contraseña debe tener al menos 8 caracteres.')
    .max(128, 'La contraseña no puede superar los 128 caracteres.'),
  rol: z.enum(ROLES, {
    errorMap: () => ({ message: 'Seleccioná un rol válido.' }),
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

/**
 * Possible values of `AdminUsuarioRead.estado`. Mirrors the bi-temporal
 * close+insert states written by `repo.versioned.close_and_insert`:
 * the row being closed gets `estado='inactivo'`, the new open row gets
 * `estado='activo'`. In practice `GET /admin/usuarios` only returns rows
 * with `vigente_hasta IS NULL`, which `close_and_insert` always stamps
 * `estado='activo'` -- so every row the list endpoint returns today has
 * `estado === 'activo'`. `'inactivo'` is kept in the filter domain for
 * forward-compat with a future "incluir inactivos" query param; the
 * table-level "Estado" filter is a documented no-op against today's data.
 */
export const ESTADOS = ['activo', 'inactivo'] as const;
export type Estado = (typeof ESTADOS)[number];

/**
 * Per-step schemas for the 3-step creation wizard (HU-F16.2:
 * `DatosPersonalesStep` -> `RolStep` -> `SucursalesStep`).
 *
 * Each one `.pick()`s its fields straight off `adminUsuarioCreateSchema`
 * instead of re-declaring the validation rules -- the wizard therefore
 * can never drift out of sync with the single-shot payload the backend
 * actually accepts (`AdminUsuarioCreateRequest` in
 * `backend/.../schemas/admin.py`). The final submit still merges all
 * three step payloads into one object validated by
 * `adminUsuarioCreateSchema` before the HTTP call.
 */
export const datosPersonalesStepSchema = adminUsuarioCreateSchema.pick({
  email: true,
  password: true,
  nombre: true,
  apellido: true,
  cedula: true,
});
export type DatosPersonalesStepInput = z.infer<typeof datosPersonalesStepSchema>;

export const rolStepSchema = adminUsuarioCreateSchema.pick({ rol: true });
export type RolStepInput = z.infer<typeof rolStepSchema>;

export const sucursalesStepSchema = adminUsuarioCreateSchema.pick({
  sucursales_asignadas: true,
});
export type SucursalesStepInput = z.infer<typeof sucursalesStepSchema>;
