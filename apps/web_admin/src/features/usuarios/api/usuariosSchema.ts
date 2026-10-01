import { z } from 'zod';

// Schema aligned with backend AdminUsuarioRead (schemas/admin.py:63-82)
export const usuarioSchema = z.object({
  uuid: z.string().uuid(),
  nombre: z.string().nullable(),
  apellido: z.string().nullable(),
  cedula: z.string().nullable(),
  email: z.string().nullable(),
  rol: z.string().nullable(),
  vigente_desde: z.string(),
  vigente_hasta: z.string().nullable(),
  estado: z.string(),
  created_at: z.string(),
  created_by: z.string().uuid().nullable(),
  sync_status: z.string().nullable(),
});

export type Usuario = z.infer<typeof usuarioSchema>;

export const usuarioListSchema = z.object({
  items: z.array(usuarioSchema),
  next_cursor: z.string().nullable().optional(),
});

export type UsuarioListResponse = z.infer<typeof usuarioListSchema>;

export const usuarioCreateSchema = z.object({
  email: z.string().email(),
  password: z.string().min(8),
  nombre: z.string().optional(),
  apellido: z.string().optional(),
  cedula: z.string().optional(),
  rol: z.string(),
});

export type UsuarioCreate = z.infer<typeof usuarioCreateSchema>;

// Update payload. Mirrors the nullable read model (`AdminUsuarioRead`
// types every field as `str | None`), so the edit form can pre-fill
// straight from the GET without a lossy cast — and clearing a field is
// expressible as an explicit `null` rather than an empty string.
export const usuarioUpdateSchema = z.object({
  email: z.string().email().nullable().optional(),
  nombre: z.string().nullable().optional(),
  apellido: z.string().nullable().optional(),
  cedula: z.string().nullable().optional(),
  rol: z.string().nullable().optional(),
});

export type UsuarioUpdate = z.infer<typeof usuarioUpdateSchema>;

export const permisoSchema = z.object({
  uuid: z.string().uuid(),
  codigo: z.string().nullable(),
  descripcion: z.string().nullable(),
});

export type Permiso = z.infer<typeof permisoSchema>;

export const permisoUsuarioSchema = z.object({
  uuid: z.string().uuid(),
  uuid_usuario: z.string().uuid(),
  uuid_permiso: z.string().uuid(),
  codigo: z.string().nullable(),
  vigente_desde: z.string(),
  vigente_hasta: z.string().nullable(),
});

export type PermisoUsuario = z.infer<typeof permisoUsuarioSchema>;

export const resetPasswordResponseSchema = z.object({
  uuid_usuario: z.string().uuid(),
  temporary_password: z.string(),
  message: z.string().optional(),
});

export type ResetPasswordResponse = z.infer<typeof resetPasswordResponseSchema>;

export const sesionSchema = z.object({
  uuid: z.string().uuid(),
  uuid_usuario: z.string().uuid(),
  ip_origen: z.string().nullable(),
  user_agent: z.string().nullable(),
  creado_en: z.string(),
  ultimo_activity: z.string(),
  estado: z.string(),
});

export type Sesion = z.infer<typeof sesionSchema>;

export const loginHistoricoSchema = z.object({
  uuid: z.string().uuid(),
  timestamp_evento: z.string(),
  timestamp_cierre: z.string().nullable(),
  estado: z.string(),
  uuid_sucursal: z.string().uuid().nullable(),
});

export type LoginHistorico = z.infer<typeof loginHistoricoSchema>;

export const sucursalUsuarioSchema = z.object({
  uuid: z.string().uuid(),
  uuid_usuario: z.string().uuid(),
  uuid_sucursal: z.string().uuid(),
  vigente_desde: z.string(),
  vigente_hasta: z.string().nullable(),
});

export type SucursalUsuario = z.infer<typeof sucursalUsuarioSchema>;
