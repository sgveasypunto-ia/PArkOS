/**
 * `reimpresionSchema.ts` — minimal Zod mirror of the
 * `ReimpresionTicketRead` BE response shape (HU-X.3 / REQ-OPS-200).
 *
 * Source: `backend/.../api/v1/schemas/workflows.py::ReimpresionTicketRead`
 * (line 54, with `motivo_anulacion` and `workflow_estado` additions from
 * DEC-TKT-04 / DEC-TKT-06).
 *
 * The full body is mostly server-set; the FE only reads a few fields
 * (uuid for the toast) so a hand-rolled type is enough. If the FE grows
 * to render the chain history, this expands.
 */
export interface ReimpresionTicketRead {
  uuid: string;
  created_at: string;
  uuid_sucursal: string | null;
  uuid_ingreso: string | null;
  uuid_factura: string | null;
  uuid_usuario: string | null;
  motivo: string;
  estado: string;
  motivo_anulacion: string | null;
  workflow_estado: string | null;
}
