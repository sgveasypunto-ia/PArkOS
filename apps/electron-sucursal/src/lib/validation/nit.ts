/**
 * `validarNitModulo11()` — pure renderer-side DIAN RUT/NIT módulo-11
 * verification (HU-F8.1, BR7 / DEC-SUC-29).
 *
 * Used by `<PagoModal>` / `<Venta>` to validate the `nit_cliente` field
 * when the operator types a NIT that is NOT the consumidor-final default
 * (DEC-SUC-04). Mirrors backend `repo/nit_modulo11.py` and
 * `web_admin/src/lib/validation/nit.ts`; the backend is authoritative.
 *
 * Algorithm — official DIAN check digit:
 *   1. Take the NIT digits WITHOUT the verification digit (DV).
 *   2. Apply the weights `[3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53,
 *      59, 67, 71]` starting at the RIGHTMOST digit and moving left
 *      (cycle repeats for >15 digits).
 *   3. Sum the products; `r = sum % 11`.
 *   4. `DV = r` when `r` is 0 or 1, otherwise `DV = 11 - r` (always 0..9).
 *   5. Compare the computed DV with the supplied DV.
 *
 * History: this module (and the backend) used to compute `DV = sum % 11`
 * with the weight table reversed. That matched real NITs only by chance
 * (e.g. 900123456 gave 3, the official DV is 8). Pinned against real
 * institutional NITs in `nit.test.ts`.
 *
 * Purity contract: no DOM, network or randomness. Accepts dots, dashes and
 * whitespace (non-digits are stripped, then leading zeros). Minimum 5
 * digits; below that returns `{ok: false}` without a DV hint. Out-of-range
 * DV returns `{ok: false, dvEsperado}`. Cédulas (CC/CE/pasaporte) carry no
 * DV and never reach this function.
 */

const MIN_NIT_LEN = 5;
const DV_MIN_LEN = 1;

/**
 * DIAN módulo-11 weights; index 0 applies to the RIGHTMOST digit. 15 elements; for
 * NITs >15 digits the cycle repeats from index 0. MUST stay identical
 * to backend `repo/nit_modulo11.py::MOD11_WEIGHTS`.
 */
const WEIGHTS = [3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71] as const;

/**
 * Strip every non-digit character from `input`, then strip leading
 * zeros (mirrors backend `_normalize_nit`). Accepts dotted, dashed, and
 * whitespace-padded NITs without changing the modulo-11 result (the
 * algorithm operates purely on digits).
 */
function stripNit(input: string): string {
  const digitsOnly = input.replace(/\D+/g, '');
  const withoutLeadingZeros = digitsOnly.replace(/^0+/, '');
  return withoutLeadingZeros || '0';
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
 *          `dvEsperado` is the computed check digit (always `'0'..'9'`).
 *
 * @example
 *   validarNitModulo11('800.123.456', '5');   // → {ok: true}
 *   validarNitModulo11('800.123.456', '1');   // → {ok: false, dvEsperado: '5'}
 *   validarNitModulo11('900123456', '8');     // → {ok: true}
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

  // Compute modulo-11 DV under the DIAN algorithm, RIGHT-TO-LEFT.
  const reversedDigits = digits.split('').reverse();
  let sum = 0;
  for (let i = 0; i < reversedDigits.length; i++) {
    // `WEIGHTS[i % WEIGHTS.length]` is always defined because
    // `i < reversedDigits.length < ∞` and `WEIGHTS.length === 15 > 0`;
    // the `!` non-null assertion satisfies `noUncheckedIndexedAccess`.
    const w = WEIGHTS[i % WEIGHTS.length]!;
    sum += Number(reversedDigits[i]) * w;
  }
  const remainder = sum % 11;
  const computed = String(remainder < 2 ? remainder : 11 - remainder);

  // Validate the supplied DV is single-digit numeric.
  if (dv.length !== DV_MIN_LEN || !/^[0-9]$/.test(dv)) {
    return { ok: false, dvEsperado: computed };
  }

  if (dv === computed) {
    return { ok: true };
  }
  return { ok: false, dvEsperado: computed };
}
