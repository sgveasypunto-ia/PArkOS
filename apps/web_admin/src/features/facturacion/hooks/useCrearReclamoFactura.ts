/**
 * `useCrearReclamoFactura.ts` — REQ-OPS-202 admin action: insert
 * `prod.reclamos` row with `tipo_reclamable='factura'`.
 *
 * BE contract (`backend/.../api/v1/workflows_reclamos.py`):
 *   POST /api/v1/workflows/reclamos
 *     body: {tipo_reclamable: 'factura', uuid_reclamable: uuid, motivo: str >= 1}
 *     201: ReclamosRead
 *     403: permission_denied (missing 'registrar_reclamo')
 *     422: motivo_vacio / missing_field
 *
 * Workflow state machine: `recibido` (initial) -> {en_investigacion,
 * rechazado} -> {resuelto, rechazado}. Only the create is wired in
 * X.5; subsequent transitions (tomar_en_revision, resolver, rechazar)
 * already exist in the existing `/reclamos/:uuid` detail page and
 * don't need to be duplicated here — the new uuid_reclamo is opened
 * in `/reclamos/:uuid` so the admin can continue the workflow there.
 */
import { useState } from 'react';

import { parkosFetch } from '@/lib/fetch';

import type { ReclamoRead } from '../api/reclamoSchema';

export interface CrearReclamoFacturaInput {
  uuid_factura: string;
  motivo: string;
}

export function useCrearReclamoFactura(): {
  trigger: (input: CrearReclamoFacturaInput) => Promise<ReclamoRead>;
  isMutating: boolean;
} {
  const [isMutating, setIsMutating] = useState(false);

  const trigger = async (input: CrearReclamoFacturaInput): Promise<ReclamoRead> => {
    setIsMutating(true);
    try {
      const idempotencyKey = crypto.randomUUID();
      const raw = await parkosFetch<unknown>('/api/v1/workflows/reclamos', {
        method: 'POST',
        body: JSON.stringify({
          tipo_reclamable: 'factura',
          uuid_reclamable: input.uuid_factura,
          motivo: input.motivo,
        }),
        headers: {
          'Content-Type': 'application/json',
          'Idempotency-Key': idempotencyKey,
        },
      });
      return raw as ReclamoRead;
    } finally {
      setIsMutating(false);
    }
  };

  return { trigger, isMutating };
}
