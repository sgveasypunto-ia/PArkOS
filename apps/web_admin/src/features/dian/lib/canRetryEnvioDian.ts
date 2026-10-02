/**
 * `canRetryEnvioDian` -- UX-only gating for the "Reintentar" action
 * (HU-F20.5). The backend (`retry_envio_dian`'s own chain-tip state
 * check) is the real authority; this only decides whether the button is
 * worth showing as enabled.
 *
 * Split out of `DianQueueTable.tsx` (not co-located as a named export
 * there) so that component file stays component-only --
 * `react-refresh/only-export-components` flags a plain function export
 * living alongside a component export in the same file.
 */
import type { EnvioDianRead } from '../api/envioDianSchema';

export function canRetryEnvioDian(
  envio: Pick<EnvioDianRead, 'estado' | 'uuid_factura_electronica'>,
): boolean {
  return envio.estado === 'rechazado' && envio.uuid_factura_electronica !== null;
}
