/**
 * `useResolverAlerta.ts` — POST mutation hook for the append-only
 * "marcar revisada" transition (HU-F11.2, REQ-OPS-181 + DEC-SUC-25).
 *
 * Drift anchors resolved:
 *   - DA-F11.2-2: POST to `/api/v1/workflows/alerta` reusing the
 *     F1.1 create path. The BE handler appends a new row to
 *     `prod.alerta` with `uuid_alerta_padre` pointing at the
 *     original; the original is NEVER updated (append-only canon,
 *     `prod.alerta` is `[A]` — REVOKE DELETE per AGENTS.md).
 *   - DA-F11.2-8: the resolver invalidates the SWR cache so the
 *     panel re-fetches; the e2e S3 scenario verifies the new row
 *     exists via testcontainers Postgres SELECT.
 *   - DA-F11.2-13: only emits `estado: 'resuelta'`. REQ-26 actor
 *     check applies ONLY to `descartada`, so the resolver flow
 *     never trips the `actor_is_target` 403.
 *
 * The hook NEVER issues PUT / PATCH — DEC-SUC-25 canon.
 */
import { useCallback, useState } from 'react';
import { useSWRConfig } from 'swr';

import { ParkosHttpError, parkosFetch } from '@parkos/ui-kit/fetch';
import { useAuthStore } from '@parkos/ui-kit/store';

import type { AlertaRead, MergedAlerta } from '../../../lib/api/schemas/alertas';

export type ResolverError =
  | { kind: 'network'; cause: Error }
  | { kind: 'http'; status: number; body: string }
  | { kind: 'actor_is_target' };

export interface UseResolverAlertaResult {
  resolve: (alert: AlertaRead | MergedAlerta) => Promise<AlertaRead | null>;
  isResolving: boolean;
  error: ResolverError | undefined;
}

interface ResolverPayload {
  uuid_sucursal: string | null;
  uuid_usuario: string | null;
  uuid_alerta_padre: string;
  tipo_alerta: string;
  estado: 'resuelta';
  timestamp_evento: string;
}

function buildPayload(alert: AlertaRead | MergedAlerta): ResolverPayload {
  const authState = useAuthStore.getState() as unknown as {
    user?: { uuid?: string | null; sucursal?: { uuid?: string | null } | null };
  };
  const uuid_sucursal = alert.uuid_sucursal ?? authState.user?.sucursal?.uuid ?? null;
  const uuid_usuario = alert.uuid_usuario ?? authState.user?.uuid ?? null;
  return {
    uuid_sucursal,
    uuid_usuario,
    uuid_alerta_padre: alert.uuid,
    tipo_alerta: alert.tipo_alerta ?? 'desconocido',
    estado: 'resuelta',
    timestamp_evento: new Date().toISOString(),
  };
}

export function useResolverAlerta(): UseResolverAlertaResult {
  const { mutate } = useSWRConfig();
  const [isResolving, setIsResolving] = useState(false);
  const [error, setError] = useState<ResolverError | undefined>(undefined);

  const resolve = useCallback(
    async (alert: AlertaRead | MergedAlerta): Promise<AlertaRead | null> => {
      setIsResolving(true);
      setError(undefined);
      try {
        const payload = buildPayload(alert);
        const res = await parkosFetch<AlertaRead>('/api/v1/workflows/alerta', {
          method: 'POST',
          body: JSON.stringify(payload),
        });
        // Invalidate the SWR cache so the panel re-fetches and the
        // resolved alert disappears (the panel queries `?estado=activa`).
        await mutate(
          (key) =>
            typeof key === 'string' && key.includes('/workflows/alerta') && key.includes('estado=activa'),
        );
        return res;
      } catch (err) {
        if (err instanceof ParkosHttpError) {
          if (err.status === 403) {
            setError({ kind: 'actor_is_target' });
            return null;
          }
          setError({ kind: 'http', status: err.status, body: err.body });
          return null;
        }
        const e = err instanceof Error ? err : new Error('unknown error');
        setError({ kind: 'network', cause: e });
        return null;
      } finally {
        setIsResolving(false);
      }
    },
    [mutate],
  );

  return { resolve, isResolving, error };
}
