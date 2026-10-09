/**
 * Caja bug 3 — el backend rechaza con 422 `voucher_datafono_duplicado` un
 * voucher de datáfono ya usado hoy en la sucursal. Este helper reconoce ese
 * error (duck-typed sobre `ParkosHttpError`: `status` + `body` JSON) para que
 * cada flujo de cobro lo pinte junto al campo del voucher.
 */
export const VOUCHER_DUPLICADO_CODE = 'voucher_datafono_duplicado';

export const VOUCHER_DUPLICADO_MENSAJE_DEFECTO =
  'Este voucher ya fue registrado hoy en esta sucursal. Verifique el número del datáfono.';

export interface VoucherDuplicado {
  message: string;
  referencia: string | null;
}

export function leerVoucherDuplicado(err: unknown): VoucherDuplicado | null {
  if (typeof err !== 'object' || err === null) return null;
  const { status, body } = err as { status?: unknown; body?: unknown };
  if (status !== 422 || typeof body !== 'string') return null;
  try {
    const parsed = JSON.parse(body) as { detail?: unknown };
    const detail = (parsed.detail ?? parsed) as {
      error?: unknown;
      message?: unknown;
      referencia?: unknown;
    };
    if (detail === null || typeof detail !== 'object' || detail.error !== VOUCHER_DUPLICADO_CODE) {
      return null;
    }
    return {
      message:
        typeof detail.message === 'string' && detail.message
          ? detail.message
          : VOUCHER_DUPLICADO_MENSAJE_DEFECTO,
      referencia: typeof detail.referencia === 'string' ? detail.referencia : null,
    };
  } catch {
    return null;
  }
}
