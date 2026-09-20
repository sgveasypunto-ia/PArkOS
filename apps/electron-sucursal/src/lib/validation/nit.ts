/**
 * `validarNitModulo11()` — pure renderer-side DIAN RUT/NIT módulo-11
 * verification (HU-F8.1, BR7 / DEC-SUC-29).
 *
 * Used by `<PagoModal>` to validate the `nit_cliente` field when the
 * operator toggles the FE checkbox and types a NIT that is NOT the
 * consumidor-final default `NIT `222222222222222` (DEC-SUC-04).
 *
 * Algorithm (matches F1.10 backend `validar_nit_modulo11`):
 *   1. Take the NIT digits WITHOUT the verification digit (DV).
 *   2. Apply the published DIAN weight vector LEFT-TO-RIGHT:
 *      `[71, 67, 59, 53, 47, 43, 41, 37, 31, 29, 23, 19, 17, 13, 7, 3]`.
 *      For NITs > 16 digits the cycle repeats from 71.
 *   3. Sum the products.
 *   4. Compute `mod = sum % 11`. Then:
 *        if mod === 0 → dv = 0
 *        else if mod === 1 → dv = 1 (special case per DIAN)
 *        else → dv = 11 - mod
 *   5. Compare the computed DV with the supplied DV.
 *
 * Reference test (BR7 / plan.md:1857-1871): NIT `800.123.456-7`.
 *
 * Purity contract:
 *   - No DOM, no network, no `window`, no `crypto` (the algorithm is
 *     fully deterministic — no randomness, no I/O).
 *   - Accepts NIT input with dots, dashes, whitespace — `stripNit()`
 *     normalizes via `\D+` removal before the modulo-11 walk.
 *   - Minimum length 6 per F1.10 schema (`nit.length >= 6`); below
 *     that returns `{ok: false}` without computing DV.
 *   - DV input accepts `0`-`9` or `'0'..'9'`; out-of-range DV
 *     returns `{ok: false, dvEsperado: '<computed>'}` so the operator
 *     gets a concrete corrective hint.
 *
 * Coupling precedent: mirrors `lib/validation/placa.ts::detectarTipoVehiculo`
 * (HU-F4.1) — pure function, exported with `REGEX_*` constants when
 * needed, single-purpose. Tests live alongside in `nit.test.ts`.
 */

const MIN_NIT_LEN = 6;
const DV_MIN_LEN = 1;

/**
 * Published DIAN modulo-11 weight vector (LEFT-TO-RIGHT application).
 * 16 elements; for NITs > 16 digits the cycle repeats from index 0.
 */
const WEIGHTS = [71, 67, 59, 53, 47, 43, 41, 37, 31, 29, 23, 19, 17, 13, 7, 3] as const;

/**
 * Strip every non-digit character from `input`. Accepts dotted,
 * dashed, and whitespace-padded NITs without changing the modulo-11
 * result (the algorithm operates purely on digits).
 */
function stripNit(input: string): string {
  return input.replace(/\D+/g, '');
}

/**
 * `validarNitModulo11(input, dv)` — pure function returning
 * `{ ok: true }` when the supplied DV matches the modulo-11
 * algorithm's computation, or `{ ok: false, dvEsperado }` otherwise.
 *
 * @param input NIT digits WITHOUT the verification digit. Accepts
 *              dotted (`800.123.456`), dashed (`800-123-456-7`), or
 *              normalized (`800123456`) forms — non-digits are
 *              stripped before the algorithm runs.
 * @param dv    Verification digit. Accepts `0`-`9` or `'0'..'9'`.
 *              Out-of-range DV yields `{ok:false, dvEsperado}`.
 * @returns `{ok: true}` when computed DV matches the supplied DV.
 *          `{ok: false, dvEsperado: '<computed>'}` otherwise.
 *          `dvEsperado` is the single-char string `'0'..'9'` the
 *          operator SHOULD type to match the algorithm.
 *
 * @example
 *   validarNitModulo11('800.123.456', '7');   // → {ok: true}
 *   validarNitModulo11('800.123.456', '1');   // → {ok: false, dvEsperado: '7'}
 *   validarNitModulo11('800123456', '7');     // → {ok: true}  (normalized)
 *   validarNitModulo11('123', '0');           // → {ok: false}  (too short)
 */
export function validarNitModulo11(
  input: string,
  dv: string,
): { ok: true } | { ok: false; dvEsperado?: string } {
  const digits = stripNit(input);
  if (digits.length < MIN_NIT_LEN) {
    return { ok: false };
  }

  // Compute modulo-11 DV under the published DIAN algorithm.
  let sum = 0;
  for (let i = 0; i < digits.length; i++) {
    const w = WEIGHTS[i % WEIGHTS.length];
    sum += Number(digits[i]) * w;
  }
  const mod = sum % 11;
  let computed: string;
  if (mod === 0) computed = '0';
  else if (mod === 1) computed = '1';
  else computed = String(11 - mod);

  // Validate the supplied DV is single-digit numeric.
  if (dv.length !== DV_MIN_LEN || !/^[0-9]$/.test(dv)) {
    return { ok: false, dvEsperado: computed };
  }

  if (dv === computed) {
    return { ok: true };
  }
  return { ok: false, dvEsperado: computed };
}