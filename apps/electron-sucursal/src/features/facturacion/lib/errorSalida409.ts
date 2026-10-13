/**
 * Bug #2 — guardas mutuas entre anulación de salida y factura. El backend
 * responde 409 con `salida_anulada` (POST factura sobre una salida con
 * anulación ejecutada) o `salida_ya_pagada` (anular-no-pagada sobre una salida
 * ya facturada). Duck-typed sobre `ParkosHttpError` (`status` + `body` JSON).
 */
export type ErrorSalida409 = 'salida_anulada' | 'salida_ya_pagada';

export function leerErrorSalida409(err: unknown): ErrorSalida409 | null {
  if (typeof err !== 'object' || err === null) return null;
  const { status, body } = err as { status?: unknown; body?: unknown };
  if (status !== 409 || typeof body !== 'string') return null;
  try {
    const parsed = JSON.parse(body) as { detail?: unknown };
    const detail = (parsed.detail ?? parsed) as { error?: unknown } | null;
    if (detail === null || typeof detail !== 'object') return null;
    return detail.error === 'salida_anulada' || detail.error === 'salida_ya_pagada'
      ? detail.error
      : null;
  } catch {
    return null;
  }
}
