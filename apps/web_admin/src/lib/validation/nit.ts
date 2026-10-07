/**
 * `validarNitModulo11` — NIT (Número de Identificación Tributaria)
 * colombiano, algoritmo módulo 11 con la tabla de pesos canónica de
 * la DIAN (BR1 de HU-F15.2, `plan.md:3544`).
 *
 * Por qué módulo 11 en cliente:
 *   - El NIT se imprime en tickets y en la FE (encabezado). Un DV
 *     incorrecto tira rechazo 422 `nit_invalido` del backend, así
 *     que validarlo en cliente evita round-trip y le da al operador
 *     la explicación concreta del cálculo (no el genérico del server).
 *   - El backend re-valida igual (defense in depth). Si el algoritmo
 *     cliente y server difieren, el server gana — esta copia local
 *     es solo UX.
 *
 * Algoritmo (idéntico al backend `parkos_core/schemas/empresa.py`):
 *   1. Limpiar la entrada: dejar solo dígitos (`.`, `-`, espacios se
 *      descartan). El último dígito es el DV; el resto es el cuerpo.
 *   2. Aplicar la tabla de pesos `[3, 7, 13, 17, 19, 23, 29, 37, 41,
 *      43, 47, 53, 59, 67, 71]` desde el dígito más a la DERECHA del
 *      cuerpo, recorriendo hacia la izquierda. Si el cuerpo tiene más
 *      de 15 dígitos, los pesos ciclan desde el inicio.
 *   3. Sumar los productos.
 *   4. `mod = suma % 11`. Si `mod < 2`, el DV esperado es `mod` (0 o 1).
 *      Si `mod >= 2`, el DV esperado es `11 - mod` (resto 10 → DV 1;
 *      el DV siempre es 0..9).
 *   5. Comparar DV esperado contra DV provisto.
 *
 * Formatos aceptados (todo se normaliza a solo dígitos antes de validar):
 *   - "900123456"          (sin DV — solo se calcula el DV esperado)
 *   - "900123456-7"        (con guión)
 *   - "900.123.456-7"      (con puntos y guión, formato colombiano)
 *   - "  900 123 456 7 "   (con espacios)
 */
const NIT_WEIGHTS = [3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71] as const;

export interface NitValidationOk {
  ok: true;
  /** Cuerpo normalizado sin DV. */
  digits: string;
  /** DV provisto por el usuario (o null si no se envió). */
  dv: number | null;
  /** DV que el algoritmo espera; igual a `dv` cuando la entrada lo incluía. */
  expectedDv: number;
}

export interface NitValidationFail {
  ok: false;
  /** Cuerpo normalizado sin DV (vacío si la entrada no tenía dígitos suficientes). */
  digits: string;
  /** DV provisto por el usuario (o null si no se envió). */
  dv: number | null;
  /** DV que el algoritmo espera — para mostrar el detalle en el mensaje de error. */
  expectedDv: number | null;
  /** Razón específica del rechazo. */
  reason:
    | 'empty'
    | 'too_short'
    | 'too_long'
    | 'invalid_dv_format'
    | 'dv_mismatch';
  /** Mensaje en español listo para `<FormMessage>`. */
  message: string;
}

export type NitValidationResult = NitValidationOk | NitValidationFail;

/** Limpia la entrada a solo dígitos. `null`/`undefined` se tratan como vacío. */
export function normalizeNit(raw: string | null | undefined): string {
  if (raw === null || raw === undefined) return '';
  return raw.replace(/\D+/g, '');
}

/**
 * Calcula el dígito de verificación módulo 11 a partir del cuerpo
 * (sin DV) según el algoritmo oficial de la DIAN. Devuelve `null`
 * solo si el cuerpo está vacío; el DV resultante siempre es 0..9.
 */
export function calcularDvModulo11(body: string): number | null {
  if (body.length === 0) return null;
  let sum = 0;
  for (let i = 0; i < body.length; i += 1) {
    const digit = body.charCodeAt(body.length - 1 - i) - 48;
    const weight = NIT_WEIGHTS[i % NIT_WEIGHTS.length]!;
    sum += digit * weight;
  }
  const mod = sum % 11;
  if (mod < 2) return mod;
  return 11 - mod;
}

/**
 * Valida un NIT. Acepta formatos con/sin DV, con/sin separadores.
 * Si la entrada no incluye DV, devuelve `ok: true` con `dv: null` y
 * el `expectedDv` calculado — útil para "verificar mientras tipea"
 * o para auto-completar el DV en formularios.
 */
export function validarNitModulo11(raw: string | null | undefined): NitValidationResult {
  const cleaned = normalizeNit(raw);

  if (cleaned.length === 0) {
    return {
      ok: false,
      digits: '',
      dv: null,
      expectedDv: null,
      reason: 'empty',
      message: 'El NIT es obligatorio.',
    };
  }

  if (cleaned.length === 1) {
    return {
      ok: false,
      digits: '',
      dv: null,
      expectedDv: null,
      reason: 'too_short',
      message: 'El NIT debe tener al menos un cuerpo y un dígito de verificación.',
    };
  }

  if (cleaned.length > 16) {
    return {
      ok: false,
      digits: cleaned.slice(0, -1),
      dv: null,
      expectedDv: null,
      reason: 'too_long',
      message: 'El NIT no puede tener más de 16 dígitos.',
    };
  }

  const body = cleaned.slice(0, -1);
  const dvChar = cleaned.charAt(cleaned.length - 1);
  const dvNum = Number.parseInt(dvChar, 10);
  if (Number.isNaN(dvNum) || dvChar.length === 0) {
    return {
      ok: false,
      digits: body,
      dv: null,
      expectedDv: null,
      reason: 'invalid_dv_format',
      message: 'El dígito de verificación debe ser numérico.',
    };
  }

  const expected = calcularDvModulo11(body);
  if (expected === null) {
    return {
      ok: false,
      digits: body,
      dv: dvNum,
      expectedDv: null,
      reason: 'too_short',
      message: 'El NIT debe tener al menos un cuerpo y un dígito de verificación.',
    };
  }

  if (dvNum !== expected) {
    return {
      ok: false,
      digits: body,
      dv: dvNum,
      expectedDv: expected,
      reason: 'dv_mismatch',
      message: `DV inválido: el esperado para ${body} es ${expected}, recibiste ${dvNum}.`,
    };
  }

  return { ok: true, digits: body, dv: dvNum, expectedDv: expected };
}
