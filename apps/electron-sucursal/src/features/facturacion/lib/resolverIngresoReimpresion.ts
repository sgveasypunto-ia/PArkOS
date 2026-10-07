/**
 * `resolverIngresoReimpresion.ts` — HU-F8.3 (H10): resuelve el término
 * tipeado por el operador (placa o cupo/consecutivo de un vehículo sin
 * placa) a un `Ingreso` ACTIVO. Un ingreso que ya tiene salida registrada
 * NO se puede reimprimir (el backend responde 409
 * `ingreso_ya_tiene_salida`); aquí se distingue ese caso (`cerrado`) de
 * "no existe" (`none`) para mostrar un mensaje claro.
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
  | { kind: 'cerrado'; termino: string }
  | { kind: 'none'; termino: string };

export async function resolverIngresoReimpresion(
  termino: string,
): Promise<ResolucionReimpresion> {
  const trimmed = termino.trim();
  if (trimmed === '') {
    return { kind: 'none', termino: '' };
  }

  const placa = normalizarPlaca(trimmed);
  const [activosPlaca, activosConsecutivo] = await Promise.all([
    getIngresosByPlaca(placa, { soloActivos: true }),
    getIngresosByConsecutivo(trimmed, { soloActivos: true }),
  ]);

  const porUuid = new Map<string, Ingreso>();
  for (const row of [...activosPlaca, ...activosConsecutivo]) {
    porUuid.set(row.uuid, row);
  }

  if (porUuid.size === 0) {
    // Nada activo: ¿existe pero ya salió? Solo para elegir el mensaje.
    const [historicoPlaca, historicoConsecutivo] = await Promise.all([
      getIngresosByPlaca(placa),
      getIngresosByConsecutivo(trimmed),
    ]);
    if (historicoPlaca.length + historicoConsecutivo.length > 0) {
      return { kind: 'cerrado', termino: trimmed };
    }
    return { kind: 'none', termino: trimmed };
  }
  if (porUuid.size >= 2) {
    return { kind: 'multiple', candidatos: Array.from(porUuid.values()) };
  }
  return { kind: 'found', ingreso: Array.from(porUuid.values())[0]! };
}
