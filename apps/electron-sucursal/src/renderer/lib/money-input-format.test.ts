/**
 * `money-input-format.test.ts` — pure-function tests for the COP money
 * input formatting helpers used by `<MoneyInput />`.
 *
 * No DOM here — these are plain string/number transforms. The
 * `computeCaretPosition` expected values below were derived by running
 * the exact documented algorithm (not hand-guessed), so they are the
 * authoritative ground truth for the implementation in
 * `money-input-format.ts`.
 */
import { describe, it, expect } from 'vitest';

import {
  sanitizeMoneyInput,
  formatMoneyDisplay,
  computeCaretPosition,
} from './money-input-format';

describe('sanitizeMoneyInput', () => {
  it('strips currency symbols and thousands separators', () => {
    expect(sanitizeMoneyInput('$1.500.000')).toBe('1500000');
  });

  it('returns empty string for empty input', () => {
    expect(sanitizeMoneyInput('')).toBe('');
  });

  it('returns empty string for letters-only input', () => {
    expect(sanitizeMoneyInput('abc')).toBe('');
  });

  it('strips mixed non-digit characters, keeping only digits in order', () => {
    expect(sanitizeMoneyInput('a1b2c3')).toBe('123');
  });
});

describe('formatMoneyDisplay', () => {
  it('returns empty string for empty input', () => {
    expect(formatMoneyDisplay('')).toBe('');
  });

  it('treats "0" as equivalent to empty (not shown)', () => {
    expect(formatMoneyDisplay('0')).toBe('');
  });

  it('treats "00" (leading zeros only) as equivalent to empty', () => {
    expect(formatMoneyDisplay('00')).toBe('');
  });

  it('ignores leading zeros on a non-zero number', () => {
    expect(formatMoneyDisplay('0050000')).toBe('50.000');
  });

  it('formats a typical 6-digit number with es-CO thousands separators', () => {
    expect(formatMoneyDisplay('50000')).toBe('50.000');
  });

  it('formats a typical 7-digit number with es-CO thousands separators', () => {
    expect(formatMoneyDisplay('1500000')).toBe('1.500.000');
  });

  it('formats a single digit with no separator', () => {
    expect(formatMoneyDisplay('5')).toBe('5');
  });
});

describe('computeCaretPosition', () => {
  it('typing a new digit at the end advances the caret to the new end', () => {
    // displayBefore "50.000" (digits "50000"), caret at the end (6).
    // Typing "9" makes the raw digits "500009" -> formatted "500.009".
    expect(computeCaretPosition('500009', '50.000', 6)).toBe(7);
  });

  it('inserting a digit in the middle lands the caret right after the inserted digit, not before the separator', () => {
    // displayBefore "1.500.000" (digits "1500000"), caret right after
    // "1.5" (index 3). Inserting "9" there -> digits "15900000" ->
    // formatted "15.900.000". The caret must land right after the "9",
    // not jump past the following group separator.
    expect(computeCaretPosition('15900000', '1.500.000', 3)).toBe(4);
  });

  it('deleting a middle digit repositions the caret at the edit point, not at the end', () => {
    // displayBefore "12.345.678" (digits "12345678"). Backspacing the
    // "4" leaves digits "1235678" -> formatted "1.235.678". caretBefore
    // is the post-deletion DOM selectionStart (4), as read inside the
    // real onChange handler.
    expect(computeCaretPosition('1235678', '12.345.678', 4)).toBe(3);
  });

  it('deleting everything puts the caret at position 0', () => {
    expect(computeCaretPosition('', '50.000', 0)).toBe(0);
  });

  it('pasting a long string over a full selection lands the caret at the end', () => {
    // displayBefore "50.000" fully selected, then pasted over with
    // digits that sanitize to "1500000" -> formatted "1.500.000".
    expect(computeCaretPosition('1500000', '50.000', 6)).toBe(9);
  });
});
