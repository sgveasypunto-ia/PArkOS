/**
 * `datetimeTz.ts` — single source of truth for datetime conversion in the
 * web_admin front.
 *
 * ## Wire contract (post Commit 3 of the datetime-tz refactor)
 *
 * The backend serializes every datetime field with a UTC suffix (``Z`` or
 * ``+00:00``). The front is **only** allowed to parse these via
 * :func:`parseApiUtc` so a missing suffix does not silently fall back to
 * "naive = local" (which is the ECMAScript default and a footgun in any
 * non-UTC host). The AGENTS.md §Sync "Naive-UTC convention" is encoded
 * here: if a string has no offset, we **append ``Z``** before parsing,
 * the same way ``pg_partman`` partitions ``TIMESTAMP`` (not
 * ``TIMESTAMPTZ``) values into UTC buckets.
 *
 * ## Browser contract
 *
 * ``<input type="datetime-local">`` always operates in the **browser's
 * local timezone** per the HTML spec — the value attribute is a
 * ``YYYY-MM-DDTHH:mm`` string with no offset, the browser displays it as
 * local time and delivers it back via ``e.target.value`` as a local-time
 * string. The helpers :func:`isoToDatetimeLocal` and
 * :func:`datetimeLocalToIso` bridge between the wire contract (UTC) and
 * the browser contract (local).
 *
 * ## TZ-aware guards
 *
 * :func:`parseApiUtc` rejects obviously malformed strings (returns
 * ``null``); callers MUST treat ``null`` as "no expiry" / "no
 * timestamp" rather than calling ``.getTime()`` on it. The single
 * :func:`isAtOrBefore` helper in this module is the only place where two
 * timestamps are compared — every form that does "is the user input
 * before the row's current value" should route through this helper
 * instead of doing its own ``new Date(...).getTime()`` arithmetic, so
 * the parse + comparison semantics stay in one place.
 *
 * ## Why this file exists
 *
 * Commit history: the previous front code shipped the helpers inline
 * inside :file:`features/cupos/components/CupoForm.tsx` and
 * :file:`features/tarifas/components/TarifaForm.tsx`, with three
 * independent bugs:
 *
 *   1. ``localNowPlusMinutesAsIso`` used ``getHours()`` (LOCAL) but
 *      appended ``+00:00`` (labeling local as UTC) — wrong for any
 *      non-UTC operator.
 *   2. ``datetimeLocalToIso`` appended ``+00:00`` to whatever the input
 *      emitted, which the browser always delivers in LOCAL — wrong for
 *      any non-UTC operator.
 *   3. ``isoToDatetimeLocal`` sliced the first 16 chars of the ISO
 *      string, so a UTC value was shown to the operator as if it
 *      were local — visually correct, semantically off by N hours.
 *
 * This module replaces those four local helpers. ``TarifaForm`` and
 * ``CupoForm`` now import from here and the timezone bugs disappear.
 */

/**
 * Parse an ISO 8601 string the backend may emit and return a ``Date``
 * anchored to UTC. Naive strings (no offset) get a ``Z`` appended
 * defensively so they don't get parsed as local — the AGENTS.md
 * "Naive-UTC convention" lives here.
 *
 * @returns a `Date` whose epoch is the same UTC instant the ISO
 *   describes, or `null` when the input is missing / empty / parse
 *   fails. Callers must check for `null`; the helper never throws.
 */
export function parseApiUtc(iso: string | null | undefined): Date | null {
  if (iso === null || iso === undefined) return null;
  const trimmed = iso.trim();
  if (trimmed.length === 0) return null;
  // The wire contract (post-Commit-3) is "Z or +HH:MM always present",
  // but pre-Commit-3 the backend emits naive. The defensive append
  // lets the two versions coexist during rollout without breaking the
  // form.
  const hasOffset =
    trimmed.endsWith('Z') ||
    /[+-]\d{2}:?\d{2}$/.test(trimmed);
  const normalized = hasOffset ? trimmed : `${trimmed}Z`;
  const d = new Date(normalized);
  return Number.isNaN(d.getTime()) ? null : d;
}

/**
 * Convert an ISO 8601 string from the API into the
 * ``YYYY-MM-DDTHH:mm`` form expected by
 * ``<input type="datetime-local">``. The output reflects the
 * **browser's local timezone** because that is how the browser
 * interprets the value attribute.
 *
 * @returns the local-time string for the input, or an empty string
 *   when the input is missing / unparseable.
 */
export function isoToDatetimeLocal(iso: string | null | undefined): string {
  const d = parseApiUtc(iso);
  if (d === null) return '';
  return formatLocalParts(d, getBrowserTimeZone());
}

/**
 * Convert the value the browser emits from
 * ``<input type="datetime-local">`` (always LOCAL, per HTML spec) into
 * the canonical wire format ``YYYY-MM-DDTHH:mm:00+00:00`` (UTC).
 *
 * The trick: ``new Date(local + ':00')`` constructs a Date using the
 * host's local TZ (because the string has no offset), and
 * ``toISOString()`` then re-projects it to UTC. We slice the result
 * to match the backend's expected shape (no millis, ``+00:00``).
 */
export function datetimeLocalToIso(local: string): string {
  if (local.trim().length === 0) {
    // The form's onChange rejects empty strings upstream; this guard
    // is defensive only.
    return '';
  }
  // Reject anything that does not match the HTML spec for
  // ``<input type="datetime-local">``: ``YYYY-MM-DDTHH:mm`` (a TZ-less
  // 16-char string). Without this guard, a non-conforming input like
  // ``"not a date"`` lands in ``new Date(..., ':00')`` and silently
  // produces a 1970/2000 epoch instant — which the backend would
  // accept as "an actual date" and trip the overlap guard for
  // unrelated reasons.
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(local.trim())) {
    return '';
  }
  const d = new Date(`${local}:00`);
  if (Number.isNaN(d.getTime())) return '';
  // toISOString() gives ``YYYY-MM-DDTHH:mm:ss.sssZ``. We want the
  // canonical ``YYYY-MM-DDTHH:mm:00+00:00`` — strip the millis
  // suffix, the trailing ``Z`` and append the project-wide constant.
  return `${d.toISOString().slice(0, 16)}:00+00:00`;
}

/**
 * Local datetime ``YYYY-MM-DDTHH:mm`` representing the current instant,
 * intended for the ``<input type="datetime-local">`` default on CREATE.
 * The browser will display this in the operator's local TZ, which is
 * what we want for "right now" UX.
 */
export function localNowAsDatetimeLocal(): string {
  return formatLocalParts(new Date(), getBrowserTimeZone());
}

/**
 * ISO 8601 string with the canonical ``+00:00`` suffix representing
 * ``now + minutes`` in **real UTC** (not the local components of
 * ``now`` mislabeled as UTC — that was the previous bug). Used by the
 * EDIT modal as the pre-fill so the operator can submit without
 * touching the field and still produce a strictly forward ``+00:00``
 * boundary.
 *
 * @param minutes number of minutes to add to the current instant.
 *   May be negative.
 */
export function utcNowPlusMinutesAsIso(minutes: number): string {
  const now = new Date();
  now.setUTCMinutes(now.getUTCMinutes() + minutes);
  return formatUtcParts(now);
}

/**
 * Compare two ISO 8601 strings (one is typically the row's
 * ``vigente_desde``, the other the form's current value) and return
 * ``true`` iff the first is **at or before** the second in real UTC.
 *
 * This is the canonical "boundary-equality" check — used by the
 * :file:`features/cupos/components/CupoForm.tsx` ``isBoundaryEdit``
 * guard and by the backend's ``<=`` pre-check at
 * ``empresa.py:1143``. Both layers MUST agree on the comparison.
 *
 * @returns ``true`` when either input is unparseable, so the caller
 *   defaults to the more permissive behaviour (let the backend decide
 *   with a clean 409 instead of the front rendering a false-positive
 *   warning). Returning a real value when one side is missing would
 *   silently mask malformed payloads.
 */
export function isAtOrBefore(
  a: string | null | undefined,
  b: string | null | undefined,
): boolean {
  const da = parseApiUtc(a);
  const db = parseApiUtc(b);
  if (da === null || db === null) return true;
  return da.getTime() <= db.getTime();
}

/**
 * Format a UTC Date as ``YYYY-MM-DDTHH:mm`` interpreted in the given
 * IANA timezone. Uses the platform ``Intl.DateTimeFormat`` with
 * ``formatToParts`` so we don't pull in ``date-fns-tz`` and stay
 * compatible with Node 18+'s built-in full-icu. The ``hour12: false``
 * is critical: without it, en-US hosts would emit "7:30 PM" instead
 * of "19:30".
 */
function formatLocalParts(d: Date, timeZone: string): string {
  const fmt = new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
  const parts = fmt.formatToParts(d);
  const lookup = (type: Intl.DateTimeFormatPartTypes): string => {
    const p = parts.find((x) => x.type === type);
    return p?.value ?? '';
  };
  // Intl's "hour24" sometimes emits "24" instead of "00" for
  // midnight (a long-standing V8 quirk). Normalize that to "00" so
  // the value round-trips through the datetime-local input.
  const hour = lookup('hour') === '24' ? '00' : lookup('hour');
  return (
    `${lookup('year')}-${lookup('month')}-${lookup('day')}` +
    `T${hour}:${lookup('minute')}`
  );
}

/**
 * Format a UTC Date as ``YYYY-MM-DDTHH:mm:00+00:00`` — the wire shape
 * the backend expects for ``vigente_desde`` on PUT/POST. Always uses
 * the UTC components, never the host's local time.
 */
function formatUtcParts(d: Date): string {
  const pad = (n: number): string => String(n).padStart(2, '0');
  return (
    `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}` +
    `T${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:00+00:00`
  );
}

/**
 * Return the browser's effective IANA timezone. We default to ``UTC``
 * when ``Intl.DateTimeFormat`` is unavailable (Node < 18 test runners
 * that don't ship full-icu, for example) so the helpers are always
 * callable and TZ-aware code paths degrade gracefully.
 */
function getBrowserTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}

/**
 * Re-export the localtime shim used by ``isoToDatetimeLocal`` and
 * ``localNowAsDatetimeLocal`` so tests can verify the wall-clock
 * output under a forced ``process.env.TZ`` without the indirection.
 */
export const __testHelpers = { getBrowserTimeZone };
