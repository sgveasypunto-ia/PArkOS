/**
 * `validarIdentificacion()` — dispatcher genérico de validación de
 * documento de identificación (HU-F8.1 extendido: persona natural +
 * empresa).
 *
 * Delega a `validarNitModulo11` (dígito de verificación DIAN) cuando
 * `tipo === 'NIT'`. Para CC/CE/pasaporte solo valida formato — Colombia
 * NO tiene dígito de verificación para cédula de ciudadanía, cédula de
 * extranjería ni pasaporte; inventar uno sería un falso invariante.
 */
import { validarNitModulo11 } from './nit';

export type TipoIdentificador = 'NIT' | 'CC' | 'CE' | 'pasaporte';

export type ResultadoValidacionIdentificacion =
  | { ok: true }
  | { ok: false; dvEsperado?: string; motivo?: string };

const CC_REGEX = /^[0-9]{6,10}$/;
const ALFANUMERICO_REGEX = /^[A-Za-z0-9]{5,20}$/;

/**
 * @param tipo   Tipo de documento (`NIT` | `CC` | `CE` | `pasaporte`).
 * @param numero Número de identificación (se recorta espacios).
 * @param dv     Dígito de verificación — solo aplica (y solo se exige)
 *               para `tipo === 'NIT'`.
 */
export function validarIdentificacion(
  tipo: TipoIdentificador,
  numero: string,
  dv?: string,
): ResultadoValidacionIdentificacion {
  const trimmed = numero.trim();
  if (tipo === 'NIT') {
    return validarNitModulo11(trimmed, dv ?? '');
  }
  if (tipo === 'CC') {
    if (!CC_REGEX.test(trimmed)) {
      return { ok: false, motivo: 'cc_formato_invalido' };
    }
    return { ok: true };
  }
  // CE / pasaporte: alfanumérico, sin dígito de verificación.
  if (!ALFANUMERICO_REGEX.test(trimmed)) {
    return { ok: false, motivo: 'documento_formato_invalido' };
  }
  return { ok: true };
}
