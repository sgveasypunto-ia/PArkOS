/**
 * Abre el drawer de reimpresión para un ingreso activo ya resuelto — helper
 * compartido por `<VehiculosTipoSheet />` y la lista "Vehículos dentro".
 * El término es la placa (o el consecutivo si no hay placa), que es lo que
 * `resolverIngresoReimpresion` sabe re-buscar; sin ninguno no hay forma de
 * resolver el ingreso y la acción no aplica.
 */
import type { DashboardDrawerState } from '@/store/dashboardDrawerStore';

type IngresoReimprimible = { placa: string | null; consecutivo: string | null };

export function terminoReimpresion(ingreso: IngresoReimprimible): string | null {
  return ingreso.placa ?? ingreso.consecutivo;
}

export function openReimpresionDeIngreso(
  openDrawer: DashboardDrawerState['open'],
  anchorId: string,
  ingreso: IngresoReimprimible,
): void {
  const termino = terminoReimpresion(ingreso);
  if (termino !== null) {
    openDrawer('reimpresion', anchorId, termino);
  }
}
