/**
 * `useImprimirCierre` — wires the cierre slips (turno / diario) to the shared
 * print layer for the two caja orchestrators. Each function never throws and,
 * when the slip does not print, leaves the visible "No se pudo imprimir …"
 * notice with "Reintentar" (`ejecutarImpresion`); the cierre is never blocked.
 */
import { useAuth } from '@parkos/ui-kit/hooks';

import { ejecutarImpresion } from '../../../lib/print/avisoImpresion';
import {
  imprimirCierre,
  type CierreImpresion,
  type CierreSeccion,
} from '../../../lib/print/arqueoPrint';
import type { SesionRead } from '../api/sesionActivaApi';
import type { ArqueoSubmitResult } from './useArqueo';
import type { CierreDiarioParaImprimir } from '../pages/cierreDiarioChain';
import type { CierreTurnoParaImprimir } from '../pages/cerrarTurnoChain';

/** What the post-close summary hands over to reprint the turno ticket. */
export interface ResumenTurnoParaImprimir {
  sesion: SesionRead;
  arqueo: ArqueoSubmitResult;
  /** The rows the summary shows on screen (`buildResumenCierreSections`). */
  secciones: CierreSeccion[];
  nota?: string;
}

export function useImprimirCierre(): {
  turno: (c: CierreTurnoParaImprimir) => Promise<unknown>;
  dia: (c: CierreDiarioParaImprimir) => Promise<unknown>;
  /** Reprint of the closed-turno summary: the on-screen rows as an 80 mm ticket. */
  resumenTurno: (c: ResumenTurnoParaImprimir) => Promise<unknown>;
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
    resumenTurno: ({ sesion, arqueo, secciones, nota }) =>
      emitir('el cierre de turno', {
        tipo: 'cierre_turno',
        sucursal: nombreSucursal,
        operador,
        uuidSesion: sesion.uuid,
        aperturaIso: sesion.timestamp_apertura,
        cierreIso: sesion.timestamp_cierre,
        baseEfectivo: sesion.valor_inicial_efectivo,
        esperado: arqueo.valor_efectivo_esperado ?? null,
        reportado: arqueo.valor_efectivo_reportado ?? sesion.valor_inicial_efectivo,
        diferencia: arqueo.diferencia_efectivo ?? null,
        uuidArqueo: arqueo.uuid,
        secciones,
        nota: nota ?? null,
      }),
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
