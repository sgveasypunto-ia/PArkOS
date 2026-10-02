/**
 * `pairingSchema.ts` — Zod schemas for the HU-F19.3 "Pairing de
 * sucursales" admin surface.
 *
 * Mirrors the real backend contract (verified against source — not
 * re-derived here):
 *
 *   - `POST /api/v1/admin/pairing-tokens` — issues a token. `ttl_hours`
 *     bounds are 1..168 inclusive (`MAX_TTL_HOURS`, backend-side
 *     constant). `token` is the plaintext secret, returned ONCE on
 *     issuance and never retrievable again afterwards.
 *   - `GET  /api/v1/admin/pairing-tokens/{uuid}` — read-back status.
 *     The server strips `pairing_token_hash` from this response, so
 *     `pairingTokenReadSchema` intentionally does NOT declare that
 *     field — if a future backend regression leaked it, `z.object`'s
 *     default "strip unknown keys" behaviour would silently drop it
 *     from the parsed result rather than surfacing it to the UI.
 */
import { z } from 'zod';

/** Mirrors the backend's `MAX_TTL_HOURS` constant. */
export const MAX_TTL_HOURS = 168;

export const pairingTokenIssueResponseSchema = z.object({
  token: z.string().min(1),
  pairing_token_uuid: z.string().uuid(),
  pairing_token_hash: z.string(),
  expires_at: z.string(),
  uuid_sucursal: z.string().uuid().nullable(),
  ttl_hours: z.number(),
});

export type PairingTokenIssueResponse = z.infer<typeof pairingTokenIssueResponseSchema>;

export const pairingTokenReadSchema = z.object({
  uuid: z.string().uuid(),
  fecha_retencion_hasta: z.string(),
  created_at: z.string(),
  created_by: z.string().uuid().nullable(),
  uuid_sucursal: z.string().uuid().nullable(),
  expires_at: z.string(),
  used: z.boolean(),
  used_at: z.string().nullable(),
  revoked_at: z.string().nullable(),
  revoked_by: z.string().uuid().nullable(),
});

export type PairingTokenRead = z.infer<typeof pairingTokenReadSchema>;

/**
 * react-hook-form + zodResolver input for
 * `<GenerarPairingTokenModal />`'s step 1 form. Spanish validation
 * messages per the rest of the app's convention.
 */
export const pairingTokenIssueFormSchema = z.object({
  ttlHours: z
    .number({ invalid_type_error: 'El TTL debe ser un número.' })
    .int('El TTL debe ser un número entero de horas.')
    .min(1, 'El TTL debe ser de al menos 1 hora.')
    .max(MAX_TTL_HOURS, 'El TTL no puede superar 168 horas (7 días).'),
});

export type PairingTokenIssueFormInput = z.infer<typeof pairingTokenIssueFormSchema>;
