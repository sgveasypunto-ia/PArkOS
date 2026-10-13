/**
 * `reclamoSchema.ts` — minimal Zod mirror of the
 * `ReclamosRead` BE response (HU-X.5 / REQ-OPS-202).
 */
export interface ReclamoRead {
  uuid: string;
  created_at: string;
  uuid_sucursal: string | null;
  uuid_reclamable: string | null;
  tipo_reclamable: 'ingreso' | 'salida' | 'factura';
  motivo: string;
  estado: 'recibido' | 'en_investigacion' | 'resuelto' | 'rechazado';
  uuid_usuario: string | null;
  uuid_reclamo_padre: string | null;
  descripcion: string | null;
}
