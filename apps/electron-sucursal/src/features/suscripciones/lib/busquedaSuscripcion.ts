/**
 * Búsqueda de suscripciones por cliente (defecto 7.5): nombre, apellido,
 * nombre completo o número de identificación. Insensible a mayúsculas y
 * acentos. Se aplica sobre el listado ya cargado de la sucursal (el endpoint
 * `subscripciones-activas` no pagina), igual que `<Listado />`.
 */
export interface ClienteBuscable {
  nombre: string | null;
  apellido: string | null;
  numero_identificacion: string | null;
}

export function normalizarBusqueda(valor: string | null | undefined): string {
  return (valor ?? '')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim();
}

/** Query vacía coincide con todo. */
export function coincideBusqueda(cliente: ClienteBuscable, query: string): boolean {
  const q = normalizarBusqueda(query);
  if (!q) return true;
  const nombreCompleto = normalizarBusqueda(
    [cliente.nombre, cliente.apellido].filter(Boolean).join(' '),
  );
  return (
    nombreCompleto.includes(q) || normalizarBusqueda(cliente.numero_identificacion).includes(q)
  );
}
