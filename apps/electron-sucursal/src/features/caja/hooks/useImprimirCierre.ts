/**
 * `useImprimirCierre` — wires the cierre slips (turno / diario) to the shared
 * print layer for the two caja orchestrators. Each function never throws and,
 * when the slip does not print, leaves the visible "No se pudo imprimir …"
 * notice with "Reintentar" (`ejecutarImpresion`); the cierre is never blocked.
 */
import { useAuth } from '@parkos/ui-kit/hooks';

import { ejecutarImpresion } from '../../../lib/print/avisoImpresion';
import { imprimirCierre, type CierreImpresion } from '../../../lib/print/arqueoPrint';
import type { CierreDiarioParaImprimir } from '../pages/cierreDiarioChain';
import type { CierreTurnoParaImprimir } from '../pages/cerrarTurnoChain';

export function useImprimirCierre(): {
  turno: (c: CierreTurnoParaImprimir) => Promise<unknown>;
  dia: (c: CierreDiarioParaImprimir) => Promise<unknown>;
} {
  const { user, sucursal } = useAuth();
  const nombre = [user?.nombre, user?.apellido]
    .filter((p): p is string => typeof p === 'string' && p.trim() !== '')
    .join(' ');
  const operador = nombre !== '' ? nombre : (user?.email ?? 'Operador');
  const nombreSucursal = sucursal?.nombre ?? null;

  const emitir = (etiqueta: string, doc: CierreImpresion): Promise<unknown> =>
    ejecutarImpresion(etiqueta, () => imprimirCierre(doc));

  return {
    turno: ({ sesion, arqueo, observaciones }) =>
      emitir('el cierre de turno', {
        tipo: 'cierre_turno',
        sucursal: nombreSucursal,
        operador,
        uuidSesion: sesion.uuid,
        aperturaIso: sesion.timestamp_apertura,
        cierreIso: sesion.timestamp_cierre ?? new Date().toISOString(),
        baseEfectivo: sesion.valor_inicial_efectivo,
        esperado: arqueo.valor_efectivo_esperado ?? null,
        reportado: arqueo.valor_efectivo_reportado ?? sesion.valor_inicial_efectivo,
        diferencia: arqueo.diferencia_efectivo ?? null,
        justificacion: observaciones ?? null,
        uuidArqueo: arqueo.uuid,
      }),
    dia: ({ arqueo, valor_efectivo_reportado, justificacion }) =>
      emitir('el cierre diario', {
        tipo: 'cierre_dia',
        sucursal: nombreSucursal,
        operador,
        cierreIso: new Date().toISOString(),
        esperado: arqueo.valor_efectivo_esperado ?? null,
        reportado: arqueo.valor_efectivo_reportado ?? valor_efectivo_reportado,
        diferencia: arqueo.diferencia_efectivo ?? null,
        justificacion: justificacion ?? null,
        uuidArqueo: arqueo.uuid,
      }),
  };
}
