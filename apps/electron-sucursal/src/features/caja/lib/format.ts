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
 * Zona horaria de toda la operación de kiosko: America/Bogota
 * (Colombia, UTC-5, sin DST). El backend genera con
 * ``datetime.now(UTC).replace(tzinfo=None)`` que produce timestamps
 * naive (sin ``Z`` ni offset), que JS parsea como LOCAL TZ del
 * navegador — si el kiosko corre en cloud UTC, hay off-by-5h. Forzando
 * la TZ a Bogotá en el formateador, garantizamos que el operador del
 * mostrador ve SIEMPRE la hora colombiana, independientemente de la TZ
 * del proceso del navegador.
 *
 * DIAN spec (HU-F14): la factura electrónica se emite con timestamp
 * en hora colombiana. Esta constante es la single source of truth
 * para esa TZ en todo el FE del kiosko (HU-F1.x timestamps,
 * HU-F7.x cotizacion, HU-F8.x pago, HU-F11.x arqueo, etc.).
 */
const BOGOTA_TZ = 'America/Bogota';

/**
 * Helper interno: parsea un timestamp ISO del backend como UTC.
 *
 * El backend retorna timestamps naive (sin ``Z`` ni offset) por el
 * patrón ``datetime.now(UTC).replace(tzinfo=None)`` que Pydantic v2
 * serializa como ``'2026-09-23T02:46:50.322102'``. ECMAScript interpreta
 * ese formato como LOCAL TZ del navegador — un kiosko en UTC vería
 * la hora "cruda" pero un kiosko en otra TZ vería la hora con offset
 * incorrecto. Para garantizar consistencia, si el string no tiene
 * sufijo ``Z`` ni offset ``+HH:MM``, le añadimos ``Z`` para que JS lo
 * parsee como UTC.
 */
function parseBackendTimestampAsUtc(iso: string): string {
  if (iso.endsWith('Z') || /[+-]\d{2}:?\d{2}$/.test(iso)) {
    return iso;
  }
  return `${iso}Z`;
}

/**
 * `formatFechaHoraCorta(iso)` — DD/MM/AA HH:mm en zona horaria
 * **Bogotá (America/Bogota, UTC-5)**.
 *
 * El formato ISO 8601 completo que llega del backend
 * (`2026-09-23T02:46:50.322102Z`) es demasiado verbose para el
 * operador del kiosko; este formato compacto es legible sin perder
 * precisión (minutos, no milisegundos, no TZ offset). Además, la TZ
 * se fuerza a Bogotá para evitar el off-by-5h cuando el kiosko corre
 * en otra TZ (cloud UTC, dev UTC, etc.).
 *
 * Ejemplos:
 *   `formatFechaHoraCorta('2026-09-23T02:46:50.322102Z')` → `"22/09/26 21:46"`
 *     (UTC-5 desde el input UTC 02:46)
 *   `formatFechaHoraCorta('2026-09-23T02:46:50.322102')` → `"22/09/26 21:46"`
 *     (mismo: el sufijo ES aplicado por el parser interno)
 *   `formatFechaHoraCorta(null)` → `"—"`
 *   `formatFechaHoraCorta('invalid')` → `"—"`
 *
 * Directiva del operador 2026-09-22: el formato ISO completo no es
 * diciente para nadie — normalizar TODA fecha visible del kiosko a
 * este formato corto, en TZ Colombia.
 */
const fechaHoraBogotaFormatter = new Intl.DateTimeFormat('es-CO', {
  timeZone: BOGOTA_TZ,
  day: '2-digit',
  month: '2-digit',
  year: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});

export function formatFechaHoraCorta(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(parseBackendTimestampAsUtc(iso));
  if (isNaN(d.getTime())) return '—';
  const parts = fechaHoraBogotaFormatter.formatToParts(d);
  const get = (type: Intl.DateTimeFormatPartTypes): string =>
    parts.find((p) => p.type === type)?.value ?? '';
  const yy = get('year').slice(-2);
  return `${get('day')}/${get('month')}/${yy} ${get('hour')}:${get('minute')}`;
}

/**
 * `formatHoraCorta(iso)` — HH:mm en zona horaria **Bogotá**, para
 * lugares que solo muestran la hora (sin fecha) — ej. la lista de
 * vehículos dentro del dashboard (HH:MM del ingreso). Mismo
 * tratamiento del backend timestamp naive → UTC que
 * ``formatFechaHoraCorta``.
 *
 * Ejemplos:
 *   `formatHoraCorta('2026-09-23T02:46:50.322102Z')` → `"21:46"` (UTC-5)
 *   `formatHoraCorta(null)` → `"—"`
 */
const horaBogotaFormatter = new Intl.DateTimeFormat('es-CO', {
  timeZone: BOGOTA_TZ,
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});

export function formatHoraCorta(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(parseBackendTimestampAsUtc(iso));
  if (isNaN(d.getTime())) return '—';
  const parts = horaBogotaFormatter.formatToParts(d);
  const get = (type: Intl.DateTimeFormatPartTypes): string =>
    parts.find((p) => p.type === type)?.value ?? '';
  return `${get('hour')}:${get('minute')}`;
}