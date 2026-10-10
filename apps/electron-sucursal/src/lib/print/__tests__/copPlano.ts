import { formatCOP, formatCOPDecimal } from '../escposTemplates';

/**
 * Money as it is PRINTED: the 80 mm tickets replace the non-breaking spaces of
 * `Intl` (no printer glyph for them) with a plain space.
 */
const plano = (s: string): string => s.replace(/[\u00a0\u202f]/g, ' ');

export function copPlano(value: number): string {
  return plano(formatCOP(value));
}

export function copDecimalPlano(value: number): string {
  return plano(formatCOPDecimal(value));
}
