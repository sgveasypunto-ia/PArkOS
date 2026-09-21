/**
 * `useArqueoResumenPorSesion.ts` — sibling SWR hook for HU-F10.3
 * (REQ-OPS-163 + REQ-OPS-165, AD-1).
 *
 * Consumes the F1.13 backend `GET /caja/arqueo/resumen` endpoint and
 * returns the per-session array (`ArqueoResumenRead.sesiones[]`) that
 * the F10.1 `useArqueoResumen` aggregate schema was DRIFTED against
 * (NEW-DA-F10.3-9). F10.3 ships the corrected `.strict()` Zod schema
 * here WITHOUT mutating the legacy aggregate schema (regression
 * guard for F10.1 `ArqueoParcial.tsx` + F8.x `CierreDiarioDialog.tsx:91`).
 *
 * Drift anchors resolved:
 *   - DA-F10.3-4 — per-session shape from F1.13 backend
 *   - NEW-DA-F10.3-9 — legacy aggregate schema left untouched
 *   - DA-F10.3-3 — future-date key-gate: hook returns `data === undefined`
 *     when `fecha > today` (efficiency guard, no wasted GET round-trip).
 *
 * Mirrors the F10.1 hook policy verbatim:
 *   - parkosFetch Bearer + 401-retry-once + 5xx backoff (F2.2 invariant).
 *   - SWR deduping 10s, shouldRetryOnError excludes 401/403/404.
 *   - 401 → useAuthStore.clear() + parkos:auth:cleared event.
 */
import useSWR from 'swr';
import { z } from 'zod';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError, parkosFetch } from '@parkos/ui-kit/fetch';

/**
 * Per-session ArqueoResumenItem — every field nullable because open
 * sessions have null cierres / reportados / uuid_arqueo while closed
 * sessions have all fields populated. Mirrors the F1.13 Pydantic
 * schema at `backend/.../schemas/caja.py:328-332`.
 */
const ArqueoResumenItemSchema = z
  .object({
    uuid_sesion: z.string().uuid().nullable(),
    uuid_usuario: z.string().uuid().nullable(),
    timestamp_apertura: z.string().nullable(),
    timestamp_cierre: z.string().nullable(),
    estado: z.string().nullable(),
    valor_efectivo_esperado: z.number().nullable(),
    valor_datafono_esperado: z.number().nullable(),
    valor_efectivo_reportado: z.number().nullable(),
    valor_datafono_reportado: z.number().nullable(),
    uuid_arqueo: z.string().uuid().nullable(),
  })
  .strict();

/**
 * Top-level ArqueoResumenRead mirror — `fecha` is ISO 8601 date
 * string (FE accepts the JSON-serialized string form per REQ-OPS-165).
 * `.strict()` is the regression guard against future backend shape
 * drift (REQ-OPS-165 scenario).
 */
const ArqueoResumenPorSesionSchema = z
  .object({
    fecha: z.string(),
    uuid_sucursal: z.string().uuid(),
    sesiones: z.array(ArqueoResumenItemSchema),
    cierre_dia: ArqueoResumenItemSchema.nullable(),
  })
  .strict();

/**
 * `ArqueoResumenPorSesion` — public type alias consumed by the
 * `<CierreDiario />` page (REQ-OPS-163). Exported for testability.
 */
export type ArqueoResumenPorSesion = z.infer<typeof ArqueoResumenPorSesionSchema>;

/**
 * Returns today's local ISO date (YYYY-MM-DD) — used for the
 * future-date key-gate (DA-F10.3-3 efficiency guard). Pinned to
 * local date so the supervisor sees the same date as the active
 * branch; the page-level date picker is the source of truth.
 */
function todayISO(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

/**
 * `useArqueoResumenPorSesion` — SWR-backed hook for the per-session
 * resumen shown on the `<CierreDiario />` page.
 *
 * @param uuid_sucursal Branch uuid (or null to disable the fetch).
 * @param fecha ISO date YYYY-MM-DD (or null to disable the fetch).
 *
 * @returns `{ data, error, refresh }` mirroring the F10.1 hook
 * shape. The key-gate returns `null` when either input is null OR
 * when `fecha > today` (efficiency guard).
 */
export function useArqueoResumenPorSesion(
  uuid_sucursal: string | null,
  fecha: string | null,
): {
  data: ArqueoResumenPorSesion | undefined;
  error: Error | undefined;
  refresh: () => Promise<ArqueoResumenPorSesion | undefined>;
} {
  const accessToken = useAuthStore((s) => s.accessToken);

  // Key-gate: skip the network call when inputs are missing OR
  // when fecha is in the future (DA-F10.3-3 efficiency guard).
  const isFutureDate = fecha !== null && fecha > todayISO();
  const key =
    uuid_sucursal && fecha && accessToken && !isFutureDate
      ? `/caja/arqueo/resumen?uuid_sucursal=${encodeURIComponent(uuid_sucursal)}&fecha=${encodeURIComponent(fecha)}`
      : null;

  const { data, error, mutate } = useSWR<ArqueoResumenPorSesion>(
    key,
    async () => {
      const raw = await parkosFetch<unknown>(
        `/api/v1${key}`,
      );
      return ArqueoResumenPorSesionSchema.parse(raw);
    },
    {
      dedupingInterval: 10_000,
      shouldRetryOnError: (err) => {
        if (err instanceof ParkosHttpError) {
          return err.status !== 401 && err.status !== 403 && err.status !== 404;
        }
        return true;
      },
      onError: (err) => {
        if (err instanceof ParkosHttpError && err.status === 401) {
          useAuthStore.getState().clear();
          if (typeof window !== 'undefined') {
            window.dispatchEvent(new Event('parkos:auth:cleared'));
          }
        }
      },
    },
  );

  return {
    data,
    error,
    refresh: async () => mutate(),
  };
}