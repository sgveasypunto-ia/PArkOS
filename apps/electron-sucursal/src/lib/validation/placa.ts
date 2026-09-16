/**
 * `detectarTipoVehiculo()` — función pura de detección de tipo de vehículo
 * por placa digitada (HU-F4.1, FASE 4 — primera HU de catálogos).
 *
 * DEC-SUC-22 verbatim: detección ESTRICTA, sin tolerancia de tipeo. La
 * tolerancia `O↔0`/`I↔1`/`B↔8` pertenece a `buscarIngresoTolerante()` (Fase 7,
 * CU-02/03 salida) — funciones DISTINTAS en archivos DISTINTOS. F4.1 sienta
 * el precedent de separación clara entre las dos funciones.
 *
 * A-03 verbatim: regex hardcoded en cliente. NO hay columna de regex en
 * `prod.tipos_vehiculo` (4NF canon). Si el negocio evoluciona el patrón,
 * se actualiza en AMBOS lugares — cliente (`placa.ts`) y backend
 * (`backend/.../operacion.py:215-277`). Backend tiene su propio
 * `detectar_tipo_vehiculo()` server-side idéntico (defense in depth XR6
 * layer 4 — operacion.py:261 verbatim "Server overwrites via V5 (regex-derived
 * UUID wins over client value)").
 *
 * BR2 de CU-01 literal: "autodetección por regex es la ÚNICA fuente válida;
 * NO hay override manual del cajero; si falla, se corrige como bug". Esta
 * función NO es parametrizable, NO toma un parámetro override de tipo, NO
 * consulta red/store/DOM — UNA sola firma.
 *
 * Normalización trivial previa (DEC-F4.1-02): (a) trim inicio/fin; (b)
 * uppercase; (c) replace(/\s+/g, '') para remover TODO whitespace interno.
 * Esto cubre los casos U5 (minúsculas) y U6 (espacios) sin necesidad de
 * regex tolerantes que introducirían matches falsos.
 *
 * Reuso forward: F6.1 `<PlacaInput>` consume la función + importa las
 * constantes `REGEX_AUTO` + `REGEX_MOTO` para validación Zod local
 * (`z.string().regex(REGEX_AUTO)`). F2.x `formatCOP` y F7.x
 * `buscarIngresoTolerante` son precedents de función pura reusable.
 */

/**
 * Auto — tres letras + tres dígitos (ej. `ABC123`).
 * MUST matchear backend `operacion.py:215-277` (defense in depth XR6 layer 4).
 */
export const REGEX_AUTO = /^[A-Z]{3}[0-9]{3}$/;

/**
 * Moto — tres letras + dos dígitos + una letra (ej. `ABC12D`).
 * MUST matchear backend `operacion.py:215-277` (defense in depth XR6 layer 4).
 *
 * NOTA: la letra final NO es necesariamente `D` — el patrón acepta
 * cualquier letra `[A-Z]`. En Colombia las motos usan formatos mixtos
 * (`ABC12D`, `ABC12E`, etc.); la regex captura TODAS.
 */
export const REGEX_MOTO = /^[A-Z]{3}[0-9]{2}[A-Z]$/;

/**
 * Detecta tipo de vehículo (Auto / Moto) a partir de la placa digitada.
 *
 * Función pura determinista — sin acceso a red, store, DOM. Testeable sin
 * mocks (6 unit tests U1..U6 verbatim `plan.md:1381`).
 *
 * @param placa Placa digitada por el operador. Acepta minúsculas, espacios
 *              internos y whitespace al inicio/fin — todos normalizados
 *              antes del regex. NO acepta caracteres especiales (`@`, `.`,
 *              `-`, etc.) ni tolerancia de tipeo `O↔0`/`I↔1`/`B↔8`.
 * @returns `'Auto'` si matchea `REGEX_AUTO`, `'Moto'` si matchea `REGEX_MOTO`,
 *          `null` si ninguna regex matchea (formato inválido).
 *
 * @example
 *   detectarTipoVehiculo('ABC123');   // → 'Auto'
 *   detectarTipoVehiculo('ABC12D');   // → 'Moto'
 *   detectarTipoVehiculo('abc123');   // → 'Auto' (normalizado)
 *   detectarTipoVehiculo('  ABC123  '); // → 'Auto' (normalizado)
 *   detectarTipoVehiculo('ABCD12');   // → null (formato inválido)
 *   detectarTipoVehiculo('');         // → null (placa vacía)
 */
export function detectarTipoVehiculo(placa: string): 'Auto' | 'Moto' | null {
  const normalizada = placa.trim().toUpperCase().replace(/\s+/g, '');
  if (REGEX_AUTO.test(normalizada)) return 'Auto';
  if (REGEX_MOTO.test(normalizada)) return 'Moto';
  return null;
}
