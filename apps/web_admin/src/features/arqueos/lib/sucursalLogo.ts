/**
 * `sucursalLogo.ts` — on-demand lookup of a sucursal's logo for the
 * HU-F18.4 signed-PDF header (BR2).
 *
 * Deliberately NOT an SWR hook: the signed export is an on-demand click
 * action, not a rendered view, so a plain async fetch-on-click keeps the
 * "Exportar PDF firmado" handler simple and avoids caching a logo the
 * user never asked to see rendered on screen. Reuses the HU-F15.4
 * `documentos` API (`documentos.tipo='logo'`) already built for
 * `SucursalDocumentos.tsx` — no new backend surface.
 */
import { listDocumentosPorSucursal } from '@/features/parametrizacion/api/documentosApi';

/**
 * BR2: resolves the current logo for `uuidSucursal` as a `data:` URL, or
 * `null` when there isn't one — or when the lookup itself fails. A
 * missing/failed logo is explicitly NOT an error for the signed-PDF
 * export (BR2): it only means the document is generated without the
 * logo header, same as "no logo uploaded".
 */
export async function fetchSucursalLogoDataUrl(
  uuidSucursal: string | null,
): Promise<string | null> {
  if (!uuidSucursal) return null;
  try {
    const documentos = await listDocumentosPorSucursal(uuidSucursal);
    const logo = documentos.find((d) => d.tipo === 'logo' && d.documento_b64);
    if (!logo?.documento_b64) return null;
    return `data:${logo.formato ?? 'application/octet-stream'};base64,${logo.documento_b64}`;
  } catch {
    return null;
  }
}
