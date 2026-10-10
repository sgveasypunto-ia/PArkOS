/**
 * Scenarios of the post-close turn summary shared by the cierre-de-turno ticket
 * tests and the 80 mm preview. The sections come from the SAME builder the
 * on-screen summary uses (`buildResumenCierreSections`), so what is asserted on
 * the ticket is what the operator confirmed on screen.
 */
import i18n from 'i18next';

import '@/i18n';

import type { ResumenCierreTurnoRead } from '../../api/schemas/resumen-cierre-turno';
import type { SesionRead } from '../../../features/caja/api/sesionActivaApi';
import { buildResumenCierreSections } from '../../../features/caja/lib/resumenCierre';
import type { CierreImpresion } from '../arqueoPrint';

export const SESION_FIXTURE: SesionRead = {
  uuid: 'abc12345-6789-0abc-1234-56789abcdef0',
  uuid_sucursal: '22222222-2222-4222-8222-222222222222',
  uuid_usuario: '33333333-3333-4333-8333-333333333333',
  valor_inicial_efectivo: 50_000,
  valor_inicial_datafono: 0,
  timestamp_apertura: '2026-10-07T13:00:00Z',
  timestamp_cierre: '2026-10-07T21:30:00Z',
};

export const RESUMEN_FIXTURE: ResumenCierreTurnoRead = {
  uuid_sesion: SESION_FIXTURE.uuid,
  uuid_sucursal: SESION_FIXTURE.uuid_sucursal,
  timestamp_calculo: '2026-10-07T21:30:00',
  ingresos_count: 41,
  salidas_count: 39,
  transacciones_count: 39,
  medios_pago: [{ medio_pago: 'efectivo', pagos_count: 39, total_cop: 187_500 }],
  reversos_count: 1,
  reversos_total_cop: 4_000,
};

export interface EscenarioCierre {
  nombre: string;
  cierre: CierreImpresion;
}

function escenario(
  nombre: string,
  esperado: number,
  contado: number,
  resumen: ResumenCierreTurnoRead | null,
  observaciones?: string,
): EscenarioCierre {
  const arqueo = {
    uuid: '99999999-2222-4333-8444-555555555555',
    valor_efectivo_esperado: esperado,
    valor_efectivo_reportado: contado,
    diferencia_efectivo: contado - esperado,
  };
  const secciones = buildResumenCierreSections(
    { sesion: SESION_FIXTURE, arqueo, resumen, ...(observaciones !== undefined ? { observaciones } : {}) },
    i18n.t.bind(i18n),
  );
  return {
    nombre,
    cierre: {
      tipo: 'cierre_turno',
      sucursal: 'Sucursal Norte',
      operador: 'Operador QA',
      uuidSesion: SESION_FIXTURE.uuid,
      aperturaIso: SESION_FIXTURE.timestamp_apertura,
      cierreIso: SESION_FIXTURE.timestamp_cierre,
      baseEfectivo: SESION_FIXTURE.valor_inicial_efectivo,
      esperado,
      reportado: contado,
      diferencia: contado - esperado,
      uuidArqueo: arqueo.uuid,
      secciones,
      nota: i18n.t('caja:cerrarTurno.resumenCierre.notaElectronicos'),
    },
  };
}

export const ESCENARIOS_CIERRE: EscenarioCierre[] = [
  escenario('Caja cuadrada con detalle de pagos', 237_500, 237_500, RESUMEN_FIXTURE),
  escenario(
    'Faltante con observaciones largas',
    237_500,
    232_500,
    RESUMEN_FIXTURE,
    'Faltante en caja menor por cambio entregado a un cliente sin registrar el pago en el sistema',
  ),
  escenario('Sobrante sin detalle de pagos', 237_500, 240_000, null),
];
