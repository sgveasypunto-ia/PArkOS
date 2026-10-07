/**
 * `feEstado.ts` — operator-facing wording for the electronic-invoice (FE)
 * outcome that every charge flow now returns (transversal rule: the FE is
 * ALWAYS emitted by the backend after the payment, to the standard customer
 * ("Consumidor final") when the payer gave no data).
 *
 * The charge response carries either `factura_electronica` (emitted, DIAN
 * state `pendiente` until acknowledged) or `factura_electronica_error` +
 * `factura_electronica_pendiente=true` (emission failed: the payment stays,
 * the invoice is retried automatically and reprint is never blocked).
 */

type Translate = (key: string, opts?: Record<string, unknown>) => string;

/** Backend reason codes (`repo/fe_emision.py`). */
const MOTIVOS: Record<string, { key: string; text: string }> = {
  resolucion_facturacion_no_encontrada: {
    key: 'resolucionNoEncontrada',
    text: 'falta configurar la resolución de facturación de esta sucursal.',
  },
  numeracion_agotada: {
    key: 'numeracionAgotada',
    text: 'se agotó la numeración de la resolución de facturación; avisá para renovarla.',
  },
  resolucion_sin_prefijo: {
    key: 'resolucionSinPrefijo',
    text: 'la resolución de facturación no tiene prefijo configurado.',
  },
  missing_sucursal_context: {
    key: 'sinSucursal',
    text: 'no se pudo identificar la sucursal de la sesión.',
  },
  fe_error_inesperado: {
    key: 'inesperado',
    text: 'ocurrió un error inesperado al emitir.',
  },
};

/**
 * Non-blocking notice for a charge whose FE is NOT emitted yet.
 * `null` when the FE went out fine (no code, not pending).
 */
export function feWarningMessage(
  code: string | null | undefined,
  pendiente: boolean | null | undefined,
  t: Translate,
): string | null {
  if (!code && !pendiente) return null;
  const base = t('facturacion:fe.aviso.pendiente', {
    defaultValue: 'Factura electrónica pendiente, se reintenta sola. El cobro quedó registrado.',
  });
  const motivo = code ? MOTIVOS[code] : undefined;
  if (!motivo) return base;
  const detalle = t(`facturacion:fe.aviso.motivo.${motivo.key}`, { defaultValue: motivo.text });
  return `${base} ${t('facturacion:fe.aviso.motivoPrefijo', { defaultValue: 'Motivo:' })} ${detalle}`;
}

/** Operator-facing label of the DIAN state shown on the receipt. */
export function feEstadoLabel(
  estado: 'pendiente' | 'enviado' | 'aceptado' | 'rechazado',
  t: Translate,
): string {
  switch (estado) {
    case 'aceptado':
      return t('facturacion:fe.aviso.estado.aceptado', { defaultValue: 'Aceptada por la DIAN' });
    case 'enviado':
      return t('facturacion:fe.aviso.estado.enviado', { defaultValue: 'Enviada a la DIAN' });
    case 'rechazado':
      return t('facturacion:fe.aviso.estado.rechazado', { defaultValue: 'Rechazada por la DIAN' });
    default:
      return t('facturacion:fe.aviso.estado.pendiente', {
        defaultValue: 'Emitida, pendiente de la DIAN',
      });
  }
}
