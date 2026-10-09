/**
 * Pending "base de caja" notice. Opening a shift redirects to the dashboard as
 * soon as the session exists, so the open-shift screen cannot hold the notice:
 * it leaves a marker (the session uuid) here and the dashboard shows the notice
 * until the operator dismisses it. Survives a reload on purpose.
 */
const KEY = 'parkos:turno-base-aviso';

function storage(): Storage | null {
  try {
    return typeof window === 'undefined' ? null : window.sessionStorage;
  } catch {
    return null;
  }
}

export function marcarBaseAviso(uuidSesion: string): void {
  storage()?.setItem(KEY, uuidSesion);
}

export function baseAvisoPendiente(uuidSesion: string): boolean {
  return storage()?.getItem(KEY) === uuidSesion;
}

export function limpiarBaseAviso(): void {
  storage()?.removeItem(KEY);
}
