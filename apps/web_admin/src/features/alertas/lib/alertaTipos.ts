/**
 * Etiquetas legibles (es-CO) por `tipo_alerta` y extracción de los datos
 * relevantes del detalle (`datos_nuevos`) sin exponer UUIDs crudos.
 *
 * Tipos nuevos del backend:
 *   - `suscripcion_placa_agregada` / `suscripcion_placa_quitada` (info)
 *   - `fe_emision_fallida` (warning)
 */

export const ALERTA_TIPO_LABELS: Record<string, { key: string; fallback: string }> = {
  suscripcion_placa_agregada: {
    key: 'alertas.tipo.suscripcion_placa_agregada',
    fallback: 'Placa agregada a suscripción',
  },
  suscripcion_placa_quitada: {
    key: 'alertas.tipo.suscripcion_placa_quitada',
    fallback: 'Placa quitada de suscripción',
  },
  fe_emision_fallida: {
    key: 'alertas.tipo.fe_emision_fallida',
    fallback: 'Falló la emisión de factura electrónica',
  },
};

type Translate = (key: string, fallback: string) => string;

/** Readable label for a `tipo_alerta`; unknown types fall back to the raw code, null to "—". */
export function alertaTipoLabel(tipo: string | null | undefined, t: Translate): string {
  if (!tipo) return '—';
  const entry = ALERTA_TIPO_LABELS[tipo];
  return entry ? t(entry.key, entry.fallback) : tipo;
}

export interface AlertaDatosRelevantes {
  placa: string | null;
  /** 'agregada' | 'quitada' or the raw action text. */
  accion: string | null;
  /** Short, human-friendly reference of the subscription (not the full uuid). */
  suscripcionRef: string | null;
  uuidSucursal: string | null;
}

function str(v: unknown): string | null {
  return typeof v === 'string' && v.trim() !== '' ? v : null;
}

/** Short reference (last 8 chars) so the UI never prints a raw UUID. */
export function shortRef(uuid: string | null): string | null {
  if (uuid === null) return null;
  return uuid.length > 8 ? uuid.slice(-8) : uuid;
}

export function extraerDatosRelevantes(
  datos: Record<string, unknown> | null | undefined,
): AlertaDatosRelevantes | null {
  if (!datos) return null;
  const placa = str(datos.placa);
  const accion = str(datos.accion);
  const suscripcionRef = shortRef(str(datos.uuid_subscripcion) ?? str(datos.uuid_suscripcion));
  const uuidSucursal = str(datos.uuid_sucursal);
  if (placa === null && accion === null && suscripcionRef === null) return null;
  return { placa, accion, suscripcionRef, uuidSucursal };
}
