/**
 * Estado de una sesión (turno) en el resumen del día.
 *
 * El backend deriva `estado` de `timestamp_cierre` y lo serializa como
 * `'abierta'` / `'cerrada'` (`repo/arqueo.py::construir_resumen_sesion`).
 * Se acepta también `'cerrado'` por tolerancia con fixtures históricos.
 */
interface SesionEstadoLike {
  estado: string | null;
  timestamp_cierre: string | null;
}

export function esSesionAbierta(s: SesionEstadoLike): boolean {
  if (s.timestamp_cierre) return false;
  return s.estado !== 'cerrada' && s.estado !== 'cerrado';
}

/** `abiertas/total` de las sesiones del día (lo que muestra la fila Σ). */
export function contarSesiones(sesiones: SesionEstadoLike[]): {
  abiertas: number;
  total: number;
} {
  return {
    abiertas: sesiones.filter(esSesionAbierta).length,
    total: sesiones.length,
  };
}
