/**
 * The standard customer ("Consumidor final", CC 222222222222) is created by
 * the backend so every electronic invoice has a recipient. It is NOT a real
 * subscriber: it must never appear in the branch's client lists/searches.
 */
const NUMEROS_CONSUMIDOR_FINAL = new Set(['222222222222', '222222222222222']);

interface ClienteLike {
  numero_identificacion?: string | null;
  nombre?: string | null;
  apellido?: string | null;
}

export function esClienteEstandar(cliente: ClienteLike | null | undefined): boolean {
  if (!cliente) return false;
  const numero = (cliente.numero_identificacion ?? '').replace(/\D+/g, '');
  // By identification ONLY: a real client that merely shares the name must not vanish.
  return numero !== '' && NUMEROS_CONSUMIDOR_FINAL.has(numero);
}

export function excluirClienteEstandar<T extends { cliente: ClienteLike }>(rows: T[]): T[] {
  return rows.filter((r) => !esClienteEstandar(r.cliente));
}
