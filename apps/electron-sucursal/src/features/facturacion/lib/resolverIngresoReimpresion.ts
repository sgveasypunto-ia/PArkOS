/**
 * `resolverIngresoReimpresion.ts` — HU-F8.3 (directiva del operador
 * 2026-09-25): resuelve el término tipeado por el operador (placa o
 * cupo/consecutivo de un vehículo sin placa) a un `Ingreso` concreto,
 * INCLUYENDO ingresos ya cerrados (el caso de uso típico de esta HU es
 * un tiquete perdido días después de que el vehículo salió).
 *
 * Composición, sin tolerancia OCR (a diferencia de
 * `buscarIngresoTolerante`, HU-F7.1): el operador está reimprimiendo un
 * tiquete que ya tiene en la mano o cuyo cupo ya conoce, no tipeando una
 * placa a mano alzada. Se consultan ambos endpoints en paralelo porque
 * el término no declara si es placa o cupo.
 */
import {
  getIngresosByConsecutivo,
  getIngresosByPlaca,
  type Ingreso,
} from '../../operacion/api/ingresoActivoApi';
import { normalizarPlaca } from '../../../lib/validation/placaTolerante';

export type ResolucionReimpresion =
  | { kind: 'found'; ingreso: Ingreso }
  | { kind: 'multiple'; candidatos: Ingreso[] }
  | { kind: 'none'; termino: string };

export async function resolverIngresoReimpresion(
  termino: string,
): Promise<ResolucionReimpresion> {
  const trimmed = termino.trim();
  if (trimmed === '') {
    return { kind: 'none', termino: '' };
  }

  const [porPlaca, porConsecutivo] = await Promise.all([
    getIngresosByPlaca(normalizarPlaca(trimmed)),
    getIngresosByConsecutivo(trimmed),
  ]);

  const porUuid = new Map<string, Ingreso>();
  for (const row of [...porPlaca, ...porConsecutivo]) {
    porUuid.set(row.uuid, row);
  }

  if (porUuid.size === 0) {
    return { kind: 'none', termino: trimmed };
  }
  if (porUuid.size >= 2) {
    return { kind: 'multiple', candidatos: Array.from(porUuid.values()) };
  }
  return { kind: 'found', ingreso: Array.from(porUuid.values())[0]! };
}
