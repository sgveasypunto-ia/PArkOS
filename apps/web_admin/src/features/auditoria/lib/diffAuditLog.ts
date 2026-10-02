/**
 * `diffAuditLog.ts` -- pure field-by-field diff builder for
 * `AuditLogItem.datos_anteriores` vs `datos_nuevos` (HU-F20.4
 * `pages/LogDetalle.tsx`). Extracted so the diff logic is unit-testable
 * without mounting the page (mirrors `alertas/lib/groupAlertas.ts`).
 *
 * Unlike `sync/pages/SyncConflict.tsx`'s whole-blob JSON dump (BR2:
 * read-only, no manual resolution needed there, so a raw side-by-side
 * `JSON.stringify` is enough), HU-F20.4 explicitly asks for a
 * FIELD-BY-FIELD diff: the union of keys across both objects, one row
 * per key, flagged `changed` when the two (stringified) values differ.
 */

export interface AuditFieldDiff {
  key: string;
  before: unknown;
  after: unknown;
  changed: boolean;
}

/** Plain-text rendering for one diff cell -- NEVER `dangerouslySetInnerHTML` (OWASP). */
export function stringifyAuditValue(value: unknown): string {
  if (value === undefined) return '—';
  if (value === null) return 'null';
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

/**
 * Builds one row per key in the union of both objects' own keys, sorted
 * alphabetically for a stable render order. A key present on only one
 * side reads as `undefined` ("—") on the other -- that is still a
 * "changed" row (e.g. a field added by this event).
 */
export function diffAuditFields(
  datosAnteriores: Record<string, unknown> | null,
  datosNuevos: Record<string, unknown> | null,
): AuditFieldDiff[] {
  const before = datosAnteriores ?? {};
  const after = datosNuevos ?? {};
  const keys = Array.from(new Set([...Object.keys(before), ...Object.keys(after)])).sort();

  return keys.map((key) => {
    const b = Object.prototype.hasOwnProperty.call(before, key) ? before[key] : undefined;
    const a = Object.prototype.hasOwnProperty.call(after, key) ? after[key] : undefined;
    return {
      key,
      before: b,
      after: a,
      changed: stringifyAuditValue(b) !== stringifyAuditValue(a),
    };
  });
}
