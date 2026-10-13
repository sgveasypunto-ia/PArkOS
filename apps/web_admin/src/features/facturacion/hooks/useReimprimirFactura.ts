/**
 * `useReimprimirFactura.ts` — REQ-OPS-200 admin action: POST a
 * `prod.reimpresion_ticket` workflow row from the admin drill-down
 * page.
 *
 * BE contract (`backend/.../api/v1/workflows_reimpresion.py`):
 *   POST /api/v1/workflows/reimpresion-ticket
 *     body: {uuid_ingreso: uuid, uuid_factura: uuid | null, motivo: str >= 10}
 *     201: ReimpresionTicketRead
 *     404: ingreso_no_encontrado | factura_no_encontrada
 *     409: reimpresion_already_pending | ingreso_ya_tiene_salida
 *     422: motivo_muy_corto (Zod pre-validates min 10 client-side)
 *
 * Defense in depth (REQ-OPS-XR1): the server-side check on
 * `ctx.issuer_prefix in ('admin-', 'operador-')` is the authority; the
 * client-side `if (me.rol !== 'admin-')` hide in
 * `<FacturaAccionesMenu />` is UX, not security.
 *
 * Idempotency-Key (REQ-OPS-XR2): generated fresh per submit so a
 * double-click cannot create two reimpresion rows. Backend respects
 * the header (PR2 `IdempotencyKeyMiddleware`).
 */
import { useState } from 'react';

import { parkosFetch } from '@/lib/fetch';

import type { ReimpresionTicketRead } from '../api/reimpresionSchema';

export interface ReimprimirInput {
  uuid_ingreso: string;
  uuid_factura?: string;
  motivo: string;
}

export function useReimprimirFactura(): {
  trigger: (input: ReimprimirInput) => Promise<ReimpresionTicketRead>;
  isMutating: boolean;
} {
  const [isMutating, setIsMutating] = useState(false);

  const trigger = async (input: ReimprimirInput): Promise<ReimpresionTicketRead> => {
    setIsMutating(true);
    try {
      const idempotencyKey = crypto.randomUUID();
      const raw = await parkosFetch<unknown>(
        '/api/v1/workflows/reimpresion-ticket',
        {
          method: 'POST',
          body: JSON.stringify({
            uuid_ingreso: input.uuid_ingreso,
            uuid_factura: input.uuid_factura ?? null,
            motivo: input.motivo,
          }),
          headers: {
            'Content-Type': 'application/json',
            'Idempotency-Key': idempotencyKey,
          },
        },
      );
      return raw as ReimpresionTicketRead;
    } finally {
      setIsMutating(false);
    }
  };

  return { trigger, isMutating };
}
