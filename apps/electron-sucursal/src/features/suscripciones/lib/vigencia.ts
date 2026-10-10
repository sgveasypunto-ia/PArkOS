/**
 * `vigencia.ts` — coverage window of a subscription sale.
 *
 * Mirrors the backend rule `calcular_fecha_vencimiento`
 * (parkos_core/repo/venta_suscripcion.py): the last covered day is
 * `fecha_inicio_cobertura + plan.duracion_dias - 1` (inclusive; plan
 * duration is in CALENDAR DAYS, quantity of vehicles does not change it).
 * Pure ISO-date arithmetic in UTC, so it is immune to the browser zone/DST.
 */
const ISO_RE = /^(\d{4})-(\d{2})-(\d{2})$/;

function parseISO(iso: string): Date | null {
  const m = ISO_RE.exec(iso);
  if (!m) return null;
  const d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])));
  return Number.isNaN(d.getTime()) ? null : d;
}

/** Returns `YYYY-MM-DD` of the last covered day, or `null` on invalid input. */
export function calcularFechaFinCobertura(
  inicioISO: string,
  duracionDias: number,
): string | null {
  const inicio = parseISO(inicioISO);
  if (inicio === null || !Number.isInteger(duracionDias) || duracionDias <= 0) {
    return null;
  }
  inicio.setUTCDate(inicio.getUTCDate() + duracionDias - 1);
  return inicio.toISOString().slice(0, 10);
}

/** `YYYY-MM-DD` -> `dd/mm/aaaa` (es-CO). Returns the input if unparsable. */
export function formatFechaCO(iso: string): string {
  const m = ISO_RE.exec(iso);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : iso;
}

export type FechaFinError = 'vacia' | 'invalida' | 'antes_inicio' | 'despues_maximo';

/**
 * Local mirror of the backend rule for the editable coverage end: the
 * operator may only SHORTEN it -- `inicio <= fin <= fin calculado por el
 * plan`. The backend is the authority (422 `fecha_fin_fuera_de_rango`);
 * this only gives immediate feedback. Returns `null` when valid.
 * ISO `YYYY-MM-DD` strings compare lexicographically.
 */
export function validarFechaFin(
  finISO: string,
  inicioISO: string,
  maximoISO: string,
): FechaFinError | null {
  if (finISO === '') return 'vacia';
  if (parseISO(finISO)?.toISOString().slice(0, 10) !== finISO) return 'invalida';
  if (finISO < inicioISO) return 'antes_inicio';
  if (finISO > maximoISO) return 'despues_maximo';
  return null;
}
