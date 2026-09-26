/**
 * `pairingSchema.ts` — Zod schemas for the branch first-boot Pairing
 * Wizard (IT-2.8, REQ-OP-15).
 *
 * Mirrors the backend `sync_router.py::_PairRequest` shape:
 *   - `pairing_token`: required, non-empty (the BE rejects empty via
 *     Pydantic `min_length=1`).
 *   - `uuid_sucursal`: required, UUID.
 *   - `branch_info.*`: optional, all-None on first boot (we don't know
 *     anything about the kiosk yet). The renderer can populate from
 *     navigator.userAgent etc., but the wizard stays minimal.
 *
 * Messages are i18n KEYS (e.g. `validation.required`) so the wizard can
 * translate via `useTranslation()` at the edge.
 */
import { z } from 'zod';

export const pairingRequestSchema = z.object({
  pairing_token: z
    .string()
    .min(1, { message: 'validation.required' })
    .max(4096, { message: 'validation.tooLong' }),
  uuid_sucursal: z.string().uuid({ message: 'validation.uuid.invalid' }),
});

export type PairingRequestInput = z.infer<typeof pairingRequestSchema>;
