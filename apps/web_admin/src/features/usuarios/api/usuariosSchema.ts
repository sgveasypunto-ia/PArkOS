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

export const usuarioUpdateSchema = z.object({
  email: z.string().email().optional(),
  nombre: z.string().optional(),
  apellido: z.string().optional(),
  cedula: z.string().optional(),
  rol: z.string().optional(),
});

export type UsuarioUpdate = z.infer<typeof usuarioUpdateSchema>;

export const permisoSchema = z.object({
  uuid: z.string().uuid(),
  codigo: z.string(),
  descripcion: z.string().nullable(),
});

export type Permiso = z.infer<typeof permisoSchema>;

export const permisoUsuarioSchema = z.object({
  uuid: z.string().uuid(),
  uuid_usuario: z.string().uuid(),
  uuid_permiso: z.string().uuid(),
  codigo: z.string(),
  vigente_desde: z.string(),
  vigente_hasta: z.string().nullable(),
});

export type PermisoUsuario = z.infer<typeof permisoUsuarioSchema>;

export const sesionSchema = z.object({
  uuid: z.string().uuid(),
  uuid_usuario: z.string().uuid(),
  ip_origen: z.string().nullable(),
  user_agent: z.string().nullable(),
  creado_en: z.string(),
  ultimo_activity: z.string(),
});

export type Sesion = z.infer<typeof sesionSchema>;

export const loginHistoricoSchema = z.object({
  uuid: z.string().uuid(),
  uuid_usuario: z.string().uuid(),
  ip_origen: z.string().nullable(),
  user_agent: z.string().nullable(),
  exitoso: z.boolean(),
  motivo_fallo: z.string().nullable(),
  creado_en: z.string(),
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
