/**
 * `printBuilder.ts` — helpers that assemble an `EntradaPayload` (the
 * ESC/POS tiquete de entrada data contract) from the data the renderer
 * has at hand after a successful 201 from `POST /operacion/ingresos`.
 *
 * REGRESSION fix (2026-09-22): the prior implementation emitted a
 * sentinel Buffer (``Buffer.from("tiquete:entrada:...")``) that the
 * `bridge.imprimir` IPC handler rejected — every click on "Imprimir"
 * failed with the generic "No se pudo imprimir el tiquete" error. This
 * helper wires the F5.2 ``escposBuilder.buildEntradaBuffer`` into the
 * actual payload contract so the IPC succeeds.
 *
 * Source of truth:
 *   - `apps/electron-sucursal/src/lib/print/escposTemplates.ts`
 *     defines ``EntradaPayload`` (discriminated union
 *     ``con-placa`` | ``con-consecutivo`` per HU-INGRESO-SIN-PLACA,
 *     REQ-OPS-197) and the 17-key strict ``TiqueteEntradaCampos``
 *     shape.
 *   - ``escposBuilder.buildEntradaBuffer(payload)`` produces the
 *     printable bytes that ``bridge.imprimir`` consumes.
 *
 * Caveats (documented TODO in code):
 *   - ``empresa``, ``sucursal.encabezado``, ``operario``, ``tarifa``,
 *     and ``documentos`` are populated with placeholders / minimal
 *     defaults because the renderer doesn't have a single
 *     consolidated "branch context" endpoint that returns all five.
 *     These should be hydrated from a future
 *     ``GET /operacion/ingresos/{uuid}/print-context`` endpoint (or
 *     each fetched individually). Today the tiquete prints with the
 *     placeholder values — acceptable in dev, flagged in the tiquete
 *     preview so the operator notices before printing.
 */
import type { EntradaPayload, Sucursal, Empresa } from './escposTemplates';
import { buildEntradaPayload } from './escposTemplates';
import type { PostIngresoResponse } from '@/features/operacion/lib/ingresoApi';

/**
 * Optional print-context metadata that the operator-facing renderer
 * may have at print time (operator name from the JWT, branch prefix
 * from the dashboard store, etc.). All fields are optional; missing
 * fields fall back to placeholders so the build NEVER fails on a
 * missing optional.
 */
export interface PrintContext {
  /** Operator display name — falls back to "Operador". */
  readonly operario?: string;
  /** Branch prefix (e.g. "D2049f2") for the tiquete header. */
  readonly sucursalEncabezado?: string;
  /** Branch horario de atención — falls back to "24h". */
  readonly horarioAtencion?: string;
}

/**
 * Optional cliente metadata fetched when ``uuid_subscripcion_cliente
 * IS NOT NULL``. When provided, the tiquete shows
 * ``Cliente: <nombre> <apellido>`` + ``CC: <numero_identificacion>``
 * + a ``*** PAGO CON MENSUALIDAD ***`` sello (driven by the response's
 * presence of ``uuid_subscripcion_cliente``).
 */
export interface ClienteContext {
  readonly nombre: string;
  readonly apellido: string;
  readonly tipoIdentificador: 'CC' | 'CE' | 'NIT' | 'PAS' | string;
  readonly numeroIdentificacion: string;
}

/**
 * Minimal default Empresa — until a ``GET /empresa/{uuid}`` endpoint
 * is wired, the tiquete carries these placeholders. The string values
 * are intentionally non-empty so ``empresaSchema.parse()`` (which
 * enforces ``z.string().min(1)``) passes.
 */
const DEFAULT_EMPRESA: Empresa = {
  nombre: 'Parkos S.A.S.',
  nit: '900.000.000-1',
  direccion: 'Sin direccion registrada',
  regimen: 'Comun',
};

const DEFAULT_SUCURSAL_ENCABEZADO = 'Sucursal';
const DEFAULT_HORARIO = '24h';

/**
 * `buildEntradaPayloadFromResponse(response, placa, context, cliente)`
 * — assemble an `EntradaPayload` from the renderer-side state after a
 * successful ingreso POST. Picks the correct discriminated-union
 * variant based on whether `placa` is present (legacy F6.2 path) or
 * the response carries `consecutivo` (HU-INGRESO-SIN-PLACA path).
 *
 * Returns the typed payload — the caller passes it to
 * ``escposBuilder.buildEntradaBuffer`` to produce the printable bytes.
 */
export function buildEntradaPayloadFromResponse(
  response: PostIngresoResponse,
  placa: string | null,
  context: PrintContext = {},
  cliente: ClienteContext | null = null,
): EntradaPayload {
  const fechaHora = new Date().toISOString();
  const sucursal: Sucursal = {
    encabezado: context.sucursalEncabezado ?? DEFAULT_SUCURSAL_ENCABEZADO,
  };

  // Common inputs for the factory.
  const base = {
    fechaEntrada: fechaHora,
    qrDataUrl: '', // caller rasterizes QR; the builder accepts empty string as
    // the documented sentinel ("logo missing" per design.md §Decision)
    logoDataUrl: '',
    empresa: DEFAULT_EMPRESA,
    operario: context.operario ?? 'Operador',
    tarifaAplicada: 0, // TODO: fetch from GET /empresa/tarifas-sucursal
    horarioAtencion: context.horarioAtencion ?? DEFAULT_HORARIO,
    folio: response.uuid,
    observaciones: undefined,
    esMensualidad: cliente !== null,
    sucursal,
  };

  // HU-INGRESO-SIN-PLACA — no-placa variant. Requires ``consecutivo``.
  if (placa === null && response.consecutivo !== null) {
    return {
      ...base,
      variant: 'con-consecutivo',
      placa: null,
      consecutivo: response.consecutivo,
    };
  }

  // Legacy F6.2 — con-placa variant. Coerce placa to string (the factory
  // contract guarantees ``placa`` is non-null in this branch).
  return {
    ...base,
    variant: 'con-placa',
    placa: placa ?? '',
  };
}
