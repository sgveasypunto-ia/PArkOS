/**
 * `format.ts` — helpers de formato compartido (F3.3 — T1).
 *
 * `formatCOP(value)` — Intl.NumberFormat es-CO moneda colombiana sin
 * decimales para efectivo/datáfono kiosko (DEC-F3.3-05). Backend persiste
 * NUMERIC(18,4) per `modelo_datos_er.mmd`; UI kiosko limita display a 0
 * decimales.
 *
 * `formatTiempoTranscurrido(fecha)` — wrapper ligero para "hace N minutos"
 * usado por `<TurnoActivoPanel>` y `<CerrarTurnoForm>`. Implementación
 * interna (cálculo de diferencia en segundos + pluralización es-CO) — NO
 * usa `date-fns` (no instalado en este workspace; ver sandbox F.6 caveat).
 *
 * Forward extensibility (F4.x+): si el proyecto adopta `date-fns`, este
 * wrapper puede reemplazarse por `formatDistanceToNow` con `locale: es` sin
 * cambiar el call site (mismo signature `(fecha: string | Date) => string`).
 */

const copFormatter = new Intl.NumberFormat('es-CO', {
  style: 'currency',
  currency: 'COP',
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});

/**
 * Formatea un número como COP (moneda colombiana).
 * Sin decimales para efectivo/datáfono kiosko (DB persiste NUMERIC(18,4)).
 * Ejemplo: `formatCOP(50000)` → `"$ 50.000"`.
 */
export function formatCOP(value: number): string {
  return copFormatter.format(value);
}

interface TiempoRelativo {
  segundos: number;
}

function diffSegundos(fecha: Date): TiempoRelativo {
  return { segundos: Math.max(0, Math.floor((Date.now() - fecha.getTime()) / 1000)) };
}

/**
 * "hace 2 horas", "hace 5 minutos", "recién", "hace 3 días".
 * Pluralización es-CO (singular/plural coherente con mensajes kiosko).
 * Threshold humano: < 60s "recién", < 60min "X minutos", < 24h "X horas",
 * resto "X días".
 *
 * Reemplazable por `formatDistanceToNow(fecha, { addSuffix: true, locale: es })`
 * cuando `date-fns` esté disponible (F4.x+ upgrade opportunity).
 */
export function formatTiempoTranscurrido(fecha: string | Date): string {
  const ref = typeof fecha === 'string' ? new Date(fecha) : fecha;
  const { segundos } = diffSegundos(ref);

  if (segundos < 60) return 'recién';
  const minutos = Math.floor(segundos / 60);
  if (minutos < 60) return `hace ${minutos} ${minutos === 1 ? 'minuto' : 'minutos'}`;
  const horas = Math.floor(minutos / 60);
  if (horas < 24) return `hace ${horas} ${horas === 1 ? 'hora' : 'horas'}`;
  const dias = Math.floor(horas / 24);
  return `hace ${dias} ${dias === 1 ? 'día' : 'días'}`;
}