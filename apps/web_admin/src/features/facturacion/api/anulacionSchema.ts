/**
 * `anulacionSchema.ts` — minimal Zod mirror of the
 * `AnulacionesRead` BE response (HU-X.4 / REQ-OPS-201).
 */
export interface AnulacionRead {
  uuid: string;
  created_at: string;
  uuid_sucursal: string | null;
  uuid_ingreso: string | null;
  uuid_salida: string | null;
  uuid_usuario: string | null;
  uuid_reclamable: string | null;
  tipo_anulable: 'ingreso' | 'salida';
  motivo: string;
  estado: string;
  uuid_anulacion_padre: string | null;
}
