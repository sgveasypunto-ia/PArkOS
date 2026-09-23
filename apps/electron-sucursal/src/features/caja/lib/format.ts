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

/**
 * `formatFechaHoraCorta(iso)` — DD/MM/AA HH:mm en zona horaria local
 * del kiosko (es-CO). El formato ISO 8601 completo que llega del backend
 * (`2026-09-23T02:46:50.322102Z`) es demasiado verbose para el
 * operador del kiosko; este formato compacto es legible sin perder
 * precisión (minutos, no milisegundos, no TZ offset).
 *
 * Ejemplos:
 *   `formatFechaHoraCorta('2026-09-23T02:46:50.322102Z')` → `"23/09/26 02:46"`
 *   `formatFechaHoraCorta(null)` → `"—"`
 *   `formatFechaHoraCorta('invalid')` → `"—"`
 *
 * Directiva del operador 2026-09-22: el formato ISO completo no es
 * diciente para nadie — normalizar TODA fecha visible del kiosko a
 * este formato corto. Usado en:
 *   - `<CotizacionPanel />` (vigente_desde, vigente_hasta de la
 *     tarifa aplicada + vigente_hasta de la cotizacion).
 *   - `<IngresoPanel />` (fecha_ingreso del "ingreso activo" inline).
 *   - `<TiqueteModal />` (timestamp de impresión).
 *
 * Forward extensibility (F4.x+): si el proyecto adopta `date-fns`,
 * este wrapper puede reemplazarse por `format(fecha, 'dd/MM/yy HH:mm')`
 * sin cambiar el call site.
 */
export function formatFechaHoraCorta(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '—';
  // Zona horaria local del kiosko (es-CO via Intl).
  const dd = String(d.getDate()).padStart(2, '0');
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const yy = String(d.getFullYear()).slice(-2);
  const hh = String(d.getHours()).padStart(2, '0');
  const min = String(d.getMinutes()).padStart(2, '0');
  return `${dd}/${mm}/${yy} ${hh}:${min}`;
}