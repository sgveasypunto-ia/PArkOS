/**
 * Abre el drawer de salida para un ingreso activo ya resuelto — helper
 * compartido por la búsqueda del hero (sugerencia / consecutivo), el click en
 * "Vehículos dentro" y las filas de `<VehiculosTipoSheet />`. Con placa se
 * entrega la placa; sin placa (bici/patineta) se entrega el `uuid_ingreso`
 * directo, porque no hay texto de placa que re-buscar
 * (`<SalidaPanel initialUuidIngreso>`).
 */
import type { DashboardDrawerState } from '@/store/dashboardDrawerStore';

export function openSalidaDeIngreso(
  openDrawer: DashboardDrawerState['open'],
  anchorId: string,
  ingreso: { uuid: string; placa: string | null },
): void {
  if (ingreso.placa) {
    openDrawer('salida', anchorId, ingreso.placa);
  } else {
    openDrawer('salida', anchorId, null, null, ingreso.uuid);
  }
}
