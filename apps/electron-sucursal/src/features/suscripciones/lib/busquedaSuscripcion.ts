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

/**
 * Criterio de normalizacion (consulta y dato pasan por la misma funcion):
 * - NFD + quitar marcas combinantes: da igual que la base guarde NFC o NFD.
 *   La enie se pliega a "n" (decision documentada): "munoz" y "muñoz" encuentran
 *   "Muñoz"; el operador casi nunca puede teclear la enie y el costo es un falso
 *   positivo menor (anos/años), aceptable en un filtro de listado.
 * - Apostrofes (recto, tipografico, acento grave/agudo) se eliminan: "O'Brien",
 *   "O\u2019Brien" y "OBrien" son equivalentes.
 * - Guion se trata como espacio ("Pérez-Gómez" == "Pérez Gómez").
 * - Caracteres invisibles (zero-width, BOM, soft hyphen) se descartan; NBSP y
 *   demas espacios Unicode se colapsan a un espacio simple (\s).
 */
export function normalizarBusqueda(valor: string | null | undefined): string {
  return (valor ?? '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[\u200b-\u200d\u2060\ufeff\u00ad]/g, '')
    .replace(/['\u2018\u2019ʼ`\u00b4]/g, '')
    .replace(/-/g, ' ')
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
