/**
 * `placaTolerante.ts` — pure-function tolerant placa search (HU-F7.1, T1).
 *
 * DEC-SUC-22 verbatim separation: este archivo es DISTINTO de `placa.ts`
 * (detección ESTRICTA). La tolerancia `O↔0`/`I↔1`/`B↔8` pertenece a
 * `buscarIngresoTolerante()` (Fase 7, CU-02/03 salida). F4.1 sienta el
 * precedent de separación clara entre las dos funciones — funciones
 * DISTINTAS en archivos DISTINTOS.
 *
 * F6.1 Path 1 precedent: `generarVariantesTolerantes` produce variantes
 * determinísticas (pure function, sin I/O); `buscarIngresoTolerante`
 * compone el `getIngresosByPlaca` existente (F6.1) para resolver. Cero
 * cambio de backend.
 *
 * Normalización: `trim() + toUpperCase() + replace(/\s+/g, '')` — espejo
 * verbatim de `placa.ts:79` (DEC-F4.1-02). La duplicación es
 * intencional; DEC-SUC-22 prohibe compartir helpers entre los dos
 * archivos para mantener la separación estructural.
 */
import type { Ingreso } from '../../features/operacion/api/ingresoActivoApi';

/**
 * Tolerance map for DEC-SUC-22 confusable characters.
 *
 * Binary pairs `O↔0`, `I↔1`, `B↔8` — exported as a `const` (not enum)
 * for direct equality-test in tests and for direct reuse by callers.
 *
 * DEC-SUC-22 verbatim: "La tolerancia `O↔0`/`I↔1`/`B↔8` pertenece a
 * `buscarIngresoTolerante()` — funciones DISTINTAS en archivos DISTINTOS."
 *
 * This constant lives ONLY in `placaTolerante.ts` — `placa.ts` does NOT
 * import it (separation mandate).
 */
export const TOLERANCIA_PLACA = {
  O: '0',
  '0': 'O',
  I: '1',
  '1': 'I',
  B: '8',
  '8': 'B',
} as const;
export type CaracterTolerante = keyof typeof TOLERANCIA_PLACA;

/**
 * Discriminated union return type for `buscarIngresoTolerante`.
 *
 * - `found` — exactly one ingreso matched (via placa variant or input).
 *   Operator flow: proceed to cotizar.
 * - `multiple` — >1 unique ingresos across all variants. Operator flow:
 *   render a `<RadioGroup>` candidate list (plan.md:1668).
 * - `none` — zero variants matched. Operator flow: render
 *   `cotizar.errors.ingreso_no_encontrado` + "Crear nuevo ingreso".
 */
export type ToleranteResultado =
  | {
      kind: 'found';
      uuid_ingreso: string;
      placaReal: string;
      varianteUsada: string;
    }
  | {
      kind: 'none';
      placaProbada: string;
    }
  | {
      kind: 'multiple';
      candidatos: ReadonlyArray<{ uuid_ingreso: string; placaReal: string }>;
    };

/** DEC-F7.1-01: cap de variantes para prevenir combinatorial explosion. */
const MAX_VARIANTES_1_POSICION = 50;
/** DEC-F7.1-01: techo absoluto de la búsqueda tolerante. */
const MAX_VARIANTES_TOTAL = 729;

/**
 * Normaliza una placa digitada: trim + uppercase + strip whitespace.
 * Espejo verbatim de `placa.ts:79` (DEC-F4.1-02). NO incluye tolerancia.
 *
 * Exportada (HU-F7.1, búsqueda sin placa) para que `vehiculoMatch.ts`
 * reuse la MISMA normalización al rankear sugerencias por prefijo de
 * placa — evita reinventar la normalización en un tercer archivo.
 */
export function normalizarPlaca(placa: string): string {
  return placa.trim().toUpperCase().replace(/\s+/g, '');
}

/**
 * Pure deterministic variant generator (REQ-OPS-151).
 *
 * Returns the input placa as the first entry (no-tolerance happy path),
 * then single-position variants (1 confusable per position), then
 * two-position variants gated by a bounded heuristic. Worst-case ceiling:
 * 729 (3 confusables × 6 positions × binary × dedup). Realistic case
 * (1 typo): ≤13 variants.
 *
 * No I/O. Same input → same output. Pure function.
 */
export function generarVariantesTolerantes(placa: string): readonly string[] {
  const normalizada = normalizarPlaca(placa);
  if (normalizada === '') return [];

  const variantes: string[] = [normalizada];
  const seen = new Set<string>([normalizada]);
  const posiciones = normalizada.length;
  const caracteres = Array.from(normalizada);

  // Single-position variants: para cada posición, para cada char que
  // tiene un confusable, emitir la variante con el char reemplazado.
  let singleCount = 0;
  for (let pos = 0; pos < posiciones; pos++) {
    const ch = caracteres[pos];
    if (ch === undefined) continue;
    const confusable = TOLERANCIA_PLACA[ch as CaracterTolerante];
    if (!confusable) continue;
    const next = caracteres.slice();
    next[pos] = confusable;
    const candidata = next.join('');
    if (!seen.has(candidata)) {
      seen.add(candidata);
      variantes.push(candidata);
      singleCount++;
      if (singleCount >= MAX_VARIANTES_1_POSICION) break;
    }
  }

  // Two-position variants: bounded heuristic. Si la cantidad de variantes
  // de 1 posición excede el umbral, NO se generan variantes de 2
  // posiciones (defensivo — no se dispara en práctica para placas de 6).
  if (singleCount < MAX_VARIANTES_1_POSICION && variantes.length < MAX_VARIANTES_TOTAL) {
    for (let p1 = 0; p1 < posiciones; p1++) {
      for (let p2 = p1 + 1; p2 < posiciones; p2++) {
        const c1 = caracteres[p1];
        const c2 = caracteres[p2];
        if (c1 === undefined || c2 === undefined) continue;
        const conf1 = TOLERANCIA_PLACA[c1 as CaracterTolerante];
        const conf2 = TOLERANCIA_PLACA[c2 as CaracterTolerante];
        if (!conf1 || !conf2) continue;
        const next = caracteres.slice();
        next[p1] = conf1;
        next[p2] = conf2;
        const candidata = next.join('');
        if (!seen.has(candidata)) {
          seen.add(candidata);
          variantes.push(candidata);
          if (variantes.length >= MAX_VARIANTES_TOTAL) break;
        }
      }
      if (variantes.length >= MAX_VARIANTES_TOTAL) break;
    }
  }

  return variantes;
}

/**
 * Async resolver. Iterates variants through `getIngresosByPlaca(variante)`
 * and aggregates results. Early-exits on the first single match
 * (`kind: 'found'`); collects up to 3 candidates before deciding
 * `kind: 'multiple'` vs `kind: 'found'`.
 *
 * Behavior contract (REQ-OPS-144):
 *   - `kind: 'found'`   → exactly one variant with exactly one result.
 *   - `kind: 'multiple'`→ 2+ unique UUIDs across variants.
 *   - `kind: 'none'`    → all variants returned empty.
 *
 * The function does NOT mutate `ingreso` and does NOT call
 * `detectarTipoVehiculo` (DEC-SUC-22 strict detector stays in `placa.ts`).
 */
export async function buscarIngresoTolerante(
  placa: string,
  getIngresosByPlaca: (placa: string) => Promise<readonly Ingreso[]>,
): Promise<ToleranteResultado> {
  const normalizada = normalizarPlaca(placa);
  if (normalizada === '') {
    return { kind: 'none', placaProbada: '' };
  }

  const variantes = generarVariantesTolerantes(normalizada);
  const candidatosMap = new Map<string, { uuid_ingreso: string; placaReal: string }>();

  for (const variante of variantes) {
    const rows = await getIngresosByPlaca(variante);
    if (rows.length === 0) continue;
    for (const row of rows) {
      // `row.placa` is `string | null` on the wire (HU-INGRESO-SIN-PLACA,
      // REQ-OPS-194 -- no-placa ingresos persist `placa = NULL`). It can
      // never be `null` HERE though: `getIngresosByPlaca` calls
      // `GET /operacion/ingresos?placa=<variante>`, and the backend
      // (`operacion.py::list_ingresos`) filters with `Ingreso.placa ==
      // placa` -- a SQL equality against a non-empty `variante` (guarded
      // by the `normalizada === ''` early-return above) never matches a
      // NULL column. Guard defensively instead of asserting: if that
      // backend invariant ever changes, skip the row rather than surface
      // a bogus `placaReal: null` to the operator.
      if (row.placa === null) continue;
      if (!candidatosMap.has(row.uuid)) {
        candidatosMap.set(row.uuid, {
          uuid_ingreso: row.uuid,
          placaReal: row.placa,
        });
      }
    }
  }

  if (candidatosMap.size === 0) {
    return { kind: 'none', placaProbada: normalizada };
  }
  if (candidatosMap.size >= 2) {
    return { kind: 'multiple', candidatos: Array.from(candidatosMap.values()) };
  }

  // Exactamente 1 candidato → 'found'. `varianteUsada` es lo que el
  // operador tipeó (normalizado: trim + uppercase + strip whitespace);
  // `placaReal` es la placa del candidato encontrado en la DB. Si el
  // operador tipeó sin typo, ambas son iguales; con typo, difieren
  // (típicamente `ABC12O` tipeado vs `ABC120` real).
  const only = Array.from(candidatosMap.values())[0]!;
  return {
    kind: 'found',
    uuid_ingreso: only.uuid_ingreso,
    placaReal: only.placaReal,
    varianteUsada: normalizada,
  };
}
