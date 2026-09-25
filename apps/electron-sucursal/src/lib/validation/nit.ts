/**
 * `validarNitModulo11()` — pure renderer-side DIAN RUT/NIT módulo-11
 * verification (HU-F8.1, BR7 / DEC-SUC-29).
 *
 * Used by `<PagoModal>` to validate the `nit_cliente` field when the
 * operator toggles the FE checkbox and types a NIT that is NOT the
 * consumidor-final default `NIT `222222222222222` (DEC-SUC-04).
 *
 * Algorithm — Variant A canónica (DIAN Resolución 000175 de 2021),
 * mirrors backend `repo/nit_modulo11.py::validar_nit_modulo11` BYTE FOR
 * BYTE. This table/formula MUST stay identical to the backend's — the
 * backend is the authoritative validator for real DIAN submission, and
 * this frontend copy exists only to give the operator an inline hint
 * before the round-trip.
 *
 * BUGFIX (2026-09-25, hallado en validación en vivo Chrome DevTools):
 * this file previously implemented a DIFFERENT algorithm — a 16-weight
 * table (including `31`, which the real DIAN table does NOT have),
 * applied LEFT-TO-RIGHT, with `DV = 11 - (sum % 11)` (Variant B). It
 * happened to agree with the backend on the one NIT both were tested
 * against (`800.123.456` → DV `7`, pure coincidence for that specific
 * digit sequence), which masked the divergence — an operator typing a
 * DIFFERENT real NIT (e.g. `900123456`, backend DV `3`) got a client-side
 * "valid" hint for the WRONG digit, then a confusing 422 from the
 * backend. Root cause: the frontend was never actually verified against
 * the backend module — only against its own (differently wrong) test
 * fixtures.
 *
 * Algorithm (matches backend exactly):
 *   1. Take the NIT digits WITHOUT the verification digit (DV).
 *   2. Apply the DIAN weight vector RIGHT-TO-LEFT:
 *      `[71, 67, 59, 53, 47, 43, 41, 37, 29, 23, 19, 17, 13, 7, 3]`
 *      (15 elements — no `31`). For NITs >15 digits the cycle repeats.
 *   3. Sum the products.
 *   4. `DV = sum % 11` directly (0..10) — NOT `11 - mod`.
 *   5. Compare the computed DV with the supplied DV.
 *
 * Reference test (BR7 / plan.md:1857-1871): NIT `800.123.456-7`.
 *
 * Purity contract:
 *   - No DOM, no network, no `window`, no `crypto` (the algorithm is
 *     fully deterministic — no randomness, no I/O).
 *   - Accepts NIT input with dots, dashes, whitespace — `stripNit()`
 *     normalizes via `\D+` removal + leading-zero strip (mirrors
 *     backend `_normalize_nit`) before the modulo-11 walk.
 *   - Minimum length 5 (mirrors backend `dv_esperado`'s minimum);
 *     below that returns `{ok: false}` without computing DV.
 *   - DV input accepts `0`-`9` or `'0'..'9'`; out-of-range DV
 *     returns `{ok: false, dvEsperado: '<computed>'}` so the operator
 *     gets a concrete corrective hint.
 *
 * Coupling precedent: mirrors `lib/validation/placa.ts::detectarTipoVehiculo`
 * (HU-F4.1) — pure function, exported with `REGEX_*` constants when
 * needed, single-purpose. Tests live alongside in `nit.test.ts`.
 */

const MIN_NIT_LEN = 5;
const DV_MIN_LEN = 1;

/**
 * DIAN módulo-11 weights, RIGHT-TO-LEFT application. 15 elements; for
 * NITs >15 digits the cycle repeats from index 0. MUST stay identical
 * to backend `repo/nit_modulo11.py::MOD11_WEIGHTS`.
 */
const WEIGHTS = [71, 67, 59, 53, 47, 43, 41, 37, 29, 23, 19, 17, 13, 7, 3] as const;

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
 *          `dvEsperado` is the computed check digit (usually `'0'..'9'`,
 *          may render as `'10'` for the rare NITs where the raw
 *          modulo-11 remainder is 10 — same edge case the backend
 *          exposes, not something this mirror should paper over).
 *
 * @example
 *   validarNitModulo11('800.123.456', '7');   // → {ok: true}
 *   validarNitModulo11('800.123.456', '1');   // → {ok: false, dvEsperado: '7'}
 *   validarNitModulo11('900123456', '3');     // → {ok: true}
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
  const computed = String(sum % 11);

  // Validate the supplied DV is single-digit numeric.
  if (dv.length !== DV_MIN_LEN || !/^[0-9]$/.test(dv)) {
    return { ok: false, dvEsperado: computed };
  }

  if (dv === computed) {
    return { ok: true };
  }
  return { ok: false, dvEsperado: computed };
}
