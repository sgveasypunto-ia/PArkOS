/**
 * `matchVehiculos` — pure ranked matching for the HU-F7.1 (búsqueda sin
 * placa) autocomplete surfaces: the dashboard `PlacaInputHero` and
 * `<SalidaPanel />`'s own `salida-placa` field.
 *
 * Two independent match strategies, applied per-item (mutually
 * exclusive in practice — an `IngresoActivo` row has either a `placa`
 * OR a `consecutivo`, never both, per REQ-OPS-197):
 *
 *   - `placa`: PREFIX match on the normalized query
 *     (`normalizarPlaca`, reused verbatim from `placaTolerante.ts` —
 *     no reinvented normalization).
 *   - `consecutivo`: SUBSTRING match, case-insensitive (the consecutivo
 *     format `<TIPO>-NNNNNN-<uuid8>` means the operator may search by
 *     tipo prefix, the numeric folio, or the trailing uuid8 fragment).
 *
 * Placa matches rank before consecutivo matches (plate-typing is the
 * dominant happy path; consecutivo search is the secondary HU-F7.1
 * flow). Result is capped at `limit` (default `MAX_VEHICULO_CANDIDATOS`)
 * so the dropdown never overflows the viewport.
 *
 * No I/O. Same input → same output. Does not mutate `items`.
 */
import { normalizarPlaca } from '../../../lib/validation/placaTolerante';
import type { IngresoActivo } from '../hooks/useIngresosActivos';

/** DEC-F7.1-05: cap de sugerencias visibles en el dropdown. */
export const MAX_VEHICULO_CANDIDATOS = 6;

export interface VehiculoMatch {
  ingreso: IngresoActivo;
  /** Which field the query matched — drives selection behavior downstream. */
  matchedOn: 'placa' | 'consecutivo';
}

/**
 * Rank `items` against the operator's typed `query`. Returns `[]` for an
 * empty/whitespace-only query (no suggestions with nothing typed).
 */
export function matchVehiculos(
  items: readonly IngresoActivo[],
  query: string,
  limit: number = MAX_VEHICULO_CANDIDATOS,
): VehiculoMatch[] {
  const trimmed = query.trim();
  if (trimmed === '') return [];

  const normalizedQuery = normalizarPlaca(trimmed);
  const lowerQuery = trimmed.toLowerCase();

  const placaMatches: VehiculoMatch[] = [];
  const consecutivoMatches: VehiculoMatch[] = [];

  for (const item of items) {
    if (
      item.placa !== null &&
      normalizarPlaca(item.placa).startsWith(normalizedQuery)
    ) {
      placaMatches.push({ ingreso: item, matchedOn: 'placa' });
      continue;
    }
    if (
      item.consecutivo !== null &&
      item.consecutivo.toLowerCase().includes(lowerQuery)
    ) {
      consecutivoMatches.push({ ingreso: item, matchedOn: 'consecutivo' });
    }
  }

  return [...placaMatches, ...consecutivoMatches].slice(0, limit);
}

/**
 * Deterministic option id shared by `<VehiculoSuggestions />` (renders
 * it on each `role="option"`) and every integration point (mirrors it
 * back via the owning `<input aria-activedescendant>`). Lives here
 * (not in the component file) so `VehiculoSuggestions.tsx` only
 * exports the component — colocating a plain helper there trips
 * `react-refresh/only-export-components`.
 */
export function vehiculoSuggestionOptionId(listboxId: string, index: number): string {
  return `${listboxId}-option-${index}`;
}

/**
 * Pure arrow-key index math shared by every integration point so the
 * up/down wraparound behavior (and the "nothing highlighted yet" seed)
 * is defined exactly once. Returns `-1` when there is nothing to
 * highlight (`length === 0`).
 */
export function getNextSuggestionIndex(
  current: number,
  direction: 'down' | 'up',
  length: number,
): number {
  if (length === 0) return -1;
  if (direction === 'down') {
    return current < length - 1 ? current + 1 : 0;
  }
  return current > 0 ? current - 1 : length - 1;
}
