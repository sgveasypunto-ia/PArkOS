/**
 * `facturaTextos.ts` — shared wording of an invoice, used by the display modal
 * AND the printed invoice so they cannot drift (FB3).
 *
 * 1. `conceptoLegible`: `factura_detalle.concepto` stores codes
 *    (`subscripcion_mensual`); the operator and the customer must read Spanish.
 * 2. `semanticaLineas`: the persisted line amounts are NOT homogeneous — parking
 *    lines store the GROSS price (IVA included) while subscription lines store
 *    the BASE (no IVA); the header `subtotal` is always the base. Persisted
 *    rows are never mutated, so the display states which one the lines are.
 */
import type { FacturaRead } from '../../features/facturacion/api/facturaApi';

const CONCEPTOS: Readonly<Record<string, string>> = {
  subscripcion_mensual: 'Suscripción mensual',
  suscripcion_mensual: 'Suscripción mensual',
  reimpresion: 'Reimpresión de tiquete',
  reimpresion_tiquete: 'Reimpresión de tiquete',
  parqueo_tiempo: 'Parqueo por tiempo',
  descuento_mensualidad: 'Descuento mensualidad',
};

/** Spanish label of a concept code; free text typed by the operator is left untouched. */
export function conceptoLegible(concepto: string | null | undefined): string {
  const raw = (concepto ?? '').trim();
  if (raw === '') return '';
  const conocido = CONCEPTOS[raw.toLowerCase()];
  if (conocido) return conocido;
  if (!raw.includes('_')) return raw;
  const texto = raw.replace(/_+/g, ' ').trim();
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}

export type SemanticaLineas = 'base' | 'bruto';

const TOLERANCIA = 0.011;

/**
 * Whether the stored line amounts are the taxable base or the gross price.
 * `null` when they reconcile with neither (no label rather than a wrong one).
 */
export function semanticaLineas(
  f: Pick<FacturaRead, 'items' | 'subtotal' | 'impuestos'>,
): SemanticaLineas | null {
  const lineas = f.items.filter((i) => i.tipo !== 'descuento');
  if (lineas.length === 0) return null;
  const suma = lineas.reduce((acc, i) => acc + Number(i.subtotal ?? 0), 0);
  const base = Number(f.subtotal ?? 0);
  if (Math.abs(suma - base) <= TOLERANCIA) return 'base';
  // Gross = base + the IVA of the gross base. The persisted tax can be the NET
  // one (AUD2: a discounted/fully covered exit carries 0), so the rate is used
  // as a second candidate.
  const impuestos = f.impuestos.reduce((acc, i) => acc + Number(i.valor ?? 0), 0);
  const tasa = Number(f.impuestos[0]?.porcentaje_aplicado ?? 0);
  const candidatos = [impuestos, base * tasa].filter((v) => v > 0);
  if (candidatos.some((iva) => Math.abs(suma - (base + iva)) <= TOLERANCIA)) return 'bruto';
  return null;
}

/**
 * Discount expressed in the same terms as the header `subtotal` (the base), so
 * the totals block reads Subtotal − Descuento + IVA = Total.
 *
 * Since AUD2 `factura_impuestos` is computed on the NET amount (total −
 * discount) while `subtotal` stays the gross base: the discount in base is the
 * difference between both. Invoices persisted before (tax on the gross base,
 * `subtotal == base`) keep the persisted `descuento` untouched.
 */
export function descuentoEnBase(
  f: Pick<FacturaRead, 'subtotal' | 'descuento' | 'impuestos'>,
): number {
  const descuento = Number(f.descuento ?? 0);
  if (!(descuento > 0)) return 0;
  if (f.impuestos.length === 0) return descuento;
  const baseNeta = Math.max(...f.impuestos.map((i) => Number(i.base_calculo ?? 0)));
  const diferencia = Number(f.subtotal ?? 0) - baseNeta;
  return diferencia > TOLERANCIA ? Math.round(diferencia * 100) / 100 : descuento;
}

export function etiquetaSemanticaLineas(s: SemanticaLineas | null): string | null {
  if (s === 'base') return 'Valores antes de IVA';
  if (s === 'bruto') return 'Valores con IVA incluido';
  return null;
}

/** Label of the header `subtotal` (always the taxable base). */
export const ETIQUETA_SUBTOTAL_BASE = 'Subtotal (base)';
