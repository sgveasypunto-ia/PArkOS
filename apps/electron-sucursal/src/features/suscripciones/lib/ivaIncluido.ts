/**
 * Desglose informativo del IVA INCLUIDO en el precio del plan.
 *
 * El precio del plan (`tipo_subscripciones.valor`) es el total que paga el
 * cliente; el IVA es un desglose dentro de él, nunca un cobro adicional.
 * Espejo de `parkos_core.repo.impuestos.desglosar_iva_incluido` (el servidor
 * es la autoridad): base = round_half_up(total / (1 + p), 2), iva = total - base.
 */
export interface DesgloseIva {
  base: number;
  iva: number;
  total: number;
}

export function desglosarIvaIncluido(total: number, porcentaje: number): DesgloseIva {
  const totalCents = Math.round(total * 100);
  const baseCents = Math.round(totalCents / (1 + porcentaje));
  return {
    base: baseCents / 100,
    iva: (totalCents - baseCents) / 100,
    total: totalCents / 100,
  };
}
