/**
 * `money-input-format.ts` — pure COP money-input formatting helpers
 * backing `<MoneyInput />` (see `components/ui/money-input.tsx`).
 *
 * Three small, dependency-free functions: strip non-digits, format
 * digits as an es-CO grouped number (no `$`, no decimals — the `$` is
 * a separate visual decoration owned by `<MoneyInput />`), and
 * recompute the caret position after a keystroke reformats the
 * display. Grouping uses `Intl.NumberFormat('es-CO', ...)` — same
 * approach as `formatCOP` in `features/caja/lib/format.ts` — so the
 * thousands separator matches the rest of the app exactly.
 */

/**
 * Strips everything that isn't a digit (0-9).
 * `"$1.500.000"` -> `"1500000"`. `""` -> `""`. `"abc"` -> `""`.
 */
export function sanitizeMoneyInput(raw: string): string {
  return (raw.match(/\d/g) ?? []).join('');
}

const moneyGroupFormatter = new Intl.NumberFormat('es-CO', {
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});

/**
 * Formats already-sanitized digits (digits only, may have leading
 * zeros) as an es-CO grouped number — no `$`, no decimals.
 * `""` -> `""`. `"0"` / `"00"` -> `""` (zero is equivalent to empty).
 * `"0050000"` -> `"50.000"` (leading zeros ignored).
 */
export function formatMoneyDisplay(digits: string): string {
  const value = Number(digits || 0);
  if (value === 0) return '';
  return moneyGroupFormatter.format(value);
}

function countDigits(s: string): number {
  return (s.match(/\d/g) ?? []).length;
}

/**
 * Recomputes where the caret should land in the newly formatted
 * display after a keystroke changed the raw digits. `displayBefore`
 * is the previously rendered (formatted) value; `caretBefore` is the
 * DOM `selectionStart` read inside the real `onChange` handler
 * (i.e. the post-edit caret position, indexed against the OLD
 * display string). This exact algorithm is validated — do not change
 * it independently of the three call-site tests in
 * `money-input-format.test.ts`.
 */
export function computeCaretPosition(
  digitsAfter: string,
  displayBefore: string,
  caretBefore: number,
): number {
  const digitsBefore = sanitizeMoneyInput(displayBefore);
  const leftDigitsOld = countDigits(displayBefore.slice(0, caretBefore));
  const delta = digitsAfter.length - digitsBefore.length;
  let target = leftDigitsOld + delta;
  target = Math.max(0, Math.min(target, digitsAfter.length));

  const newDisplay = formatMoneyDisplay(digitsAfter);
  let seen = 0;
  for (let i = 0; i < newDisplay.length; i++) {
    if (seen === target) return i;
    if (/\d/.test(newDisplay.charAt(i))) seen++;
  }
  return newDisplay.length;
}
