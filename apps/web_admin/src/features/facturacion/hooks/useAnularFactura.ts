/**
 * `useAnularFactura.ts` — REQ-OPS-201 admin action: insert
 * `prod.anulaciones` row with `tipo_anulable='salida'` for the salida
 * linked to the factura.
 *
 * BE contract (`backend/.../api/v1/workflows_anulaciones.py`):
 *   POST /api/v1/workflows/anulaciones
 *     body: {tipo_anulable: 'salida', uuid_salida: uuid, motivo: str >= 1}
 *     201: AnulacionesRead
 *     422: polymorphic pair mismatch (defense in depth at the schema layer)
 *
 * `V_FACTURA_ESTADO` view flips the factura's estado to `'anulada'`
 * automatically (derived view, no UPDATE to `prod.facturas` — append-only
 * compliance per AGENTS.md "AUDIT-FIRST canon").
 */
import { useState } from 'react';

import { parkosFetch } from '@/lib/fetch';

import type { AnulacionRead } from '../api/anulacionSchema';

export interface AnularFacturaInput {
  uuid_salida: string;
  motivo: string;
}

export function useAnularFactura(): {
  trigger: (input: AnularFacturaInput) => Promise<AnulacionRead>;
  isMutating: boolean;
} {
  const [isMutating, setIsMutating] = useState(false);

  const trigger = async (input: AnularFacturaInput): Promise<AnulacionRead> => {
    setIsMutating(true);
    try {
      const idempotencyKey = crypto.randomUUID();
      const raw = await parkosFetch<unknown>('/api/v1/workflows/anulaciones', {
        method: 'POST',
        body: JSON.stringify({
          tipo_anulable: 'salida',
          uuid_salida: input.uuid_salida,
          motivo: input.motivo,
        }),
        headers: {
          'Content-Type': 'application/json',
          'Idempotency-Key': idempotencyKey,
        },
      });
      return raw as AnulacionRead;
    } finally {
      setIsMutating(false);
    }
  };

  return { trigger, isMutating };
}
