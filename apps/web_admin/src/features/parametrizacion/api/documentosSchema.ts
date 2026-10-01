/**
 * `documentosSchema.ts` — Zod schemas + types for `prod.documentos`
 * (HU-F15.4).
 *
 * Mirrors the backend `schemas/empresa.py::DocumentosRead` /
 * `DocumentosCreate` / `DocumentosUpdate` exactly. `tipo` is kept as a
 * free `z.string()` on the READ side (the column has no DB-level enum,
 * and a future tipo should not break parsing of existing rows), but the
 * WRITE side (`documentoUpsertSchema`) narrows `tipo` to the 4 values
 * this screen manages (`DOCUMENTO_TIPOS`), since those are the only
 * values this UI ever writes.
 */
import { z } from 'zod';

import {
  DOCUMENTO_TIPOS,
  MAX_DOCUMENTO_B64_CHARS,
} from '@/lib/validation/documentos';

export const documentoTipoSchema = z.enum(DOCUMENTO_TIPOS);
export type DocumentoTipoInput = z.infer<typeof documentoTipoSchema>;

export const documentoReadSchema = z.object({
  uuid: z.string().uuid(),
  uuid_sucursal: z.string().uuid().nullable(),
  tipo: z.string().nullable(),
  formato: z.string().nullable(),
  documento_b64: z.string().nullable(),
  vigente_desde: z.string(),
  vigente_hasta: z.string().nullable(),
  estado: z.string(),
  created_at: z.string(),
  created_by: z.string().uuid().nullable(),
  sync_status: z.string().nullable(),
});
export type Documento = z.infer<typeof documentoReadSchema>;

export const documentoReadListSchema = z.object({
  items: z.array(documentoReadSchema),
  next_cursor: z.string().nullable().optional(),
});
export type DocumentoReadListEnvelope = z.infer<typeof documentoReadListSchema>;

/**
 * Same shape for create (POST) and update (PUT) — the backend's
 * `DocumentosCreate`/`DocumentosUpdate` are identical (see
 * `schemas/empresa.py`).
 */
export const documentoUpsertSchema = z.object({
  uuid_sucursal: z.string().uuid(),
  tipo: documentoTipoSchema,
  formato: z.string().max(32).nullable().optional(),
  documento_b64: z
    .string()
    .min(1, 'El documento no puede estar vacío.')
    .max(MAX_DOCUMENTO_B64_CHARS, 'El documento excede el tamaño máximo permitido.'),
});
export type DocumentoUpsertInput = z.infer<typeof documentoUpsertSchema>;
