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
import type {
  EntradaPayload,
  ReimpresionPayload,
  Sucursal,
  Empresa,
} from './escposTemplates';
import type { PostIngresoResponse } from '../../features/operacion/lib/ingresoApi';
import type { Ingreso } from '../../features/operacion/api/ingresoActivoApi';

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
 * `buildEntradaPayloadFromResponse(response, placa, context)` —
 * assemble an `EntradaPayload` from the renderer-side state after a
 * successful ingreso POST. Picks the correct discriminated-union
 * variant based on whether `placa` is present (legacy F6.2 path) or
 * the response carries `consecutivo` (HU-INGRESO-SIN-PLACA path).
 *
 * Returns the typed payload — the caller passes it to
 * ``escposBuilder.buildEntradaBuffer`` to produce the printable bytes.
 *
 * BUGFIX: this used to take an extra ``cliente: ClienteContext | null``
 * parameter and derive ``esMensualidad`` from ``cliente !== null`` —
 * removed because both call sites always passed ``null`` (cliente
 * metadata was never threaded through), which made the printed
 * tiquete NEVER show "MENSUALIDAD" regardless of the real subscription
 * status. ``esMensualidad`` now reads ``response.tipo_entrada``
 * directly (server-derived, DEC-SUC-21).
 */
export function buildEntradaPayloadFromResponse(
  response: PostIngresoResponse,
  placa: string | null,
  context: PrintContext = {},
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
    // BUGFIX (found while wiring the "Tipo: ROTACIÓN/MENSUALIDAD" ticket
    // field, operator request): this used to read ``cliente !== null``,
    // but the only call site (``IngresoPanel.tsx::buildPrintPayload``)
    // ALWAYS passes ``cliente=null`` ("cliente metadata not threaded
    // into ESC/POS payload yet" — separate unfinished feature). The
    // printed tiquete therefore NEVER showed "MENSUALIDAD" in
    // production, regardless of the vehicle's actual subscription.
    // ``response.tipo_entrada`` is the server-derived, authoritative
    // source (DEC-SUC-21) — use it directly instead.
    esMensualidad: response.tipo_entrada === 'MENSUALIDAD',
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

/**
 * `buildReimpresionEntradaPayload(ingreso, motivo, context)` — HU-F8.3
 * (directiva del operador 2026-09-25): assemble a `ReimpresionPayload`
 * (`originalTipo: 'entrada'`) for a HISTORICAL `Ingreso` found via
 * placa/cupo search (`resolverIngresoReimpresion.ts`), instead of a
 * fresh `PostIngresoResponse`.
 *
 * Mirrors `buildEntradaPayloadFromResponse` field-for-field (same
 * placeholder defaults — the print-context endpoint gap documented at
 * the top of this file applies here too), with two differences:
 *   - `fechaEntrada` uses the ORIGINAL `ingreso.fecha_ingreso` (a
 *     reprint must show when the vehicle actually entered, not the
 *     reprint moment). Re-serialized via `Date` to guarantee the
 *     `z.string().datetime({ offset: true })` contract regardless of
 *     the backend's exact timestamp string format.
 *   - `esMensualidad` is derived from `uuid_subscripcion_cliente`
 *     directly (DEC-SUC-21) since a historical `Ingreso` row has no
 *     `tipo_entrada` discriminator.
 *
 * Only `originalTipo: 'entrada'` is supported today — reprinting a
 * salida ticket needs the ORIGINAL cobro breakdown (subtotal/iva/total)
 * from `prod.facturas`/`factura_detalle`, which no renderer-side fetch
 * currently exposes by `uuid_ingreso`. Fabricating those numbers from a
 * fresh cotización would show the WRONG charged amount on a financial
 * document — out of scope here, flagged as a follow-up.
 */
export function buildReimpresionEntradaPayload(
  ingreso: Ingreso,
  motivo: string,
  context: PrintContext = {},
): ReimpresionPayload {
  const fechaEntrada = new Date(ingreso.fecha_ingreso ?? Date.now()).toISOString();
  const sucursal: Sucursal = {
    encabezado: context.sucursalEncabezado ?? DEFAULT_SUCURSAL_ENCABEZADO,
  };

  const base = {
    fechaEntrada,
    qrDataUrl: '',
    logoDataUrl: '',
    empresa: DEFAULT_EMPRESA,
    operario: context.operario ?? 'Operador',
    tarifaAplicada: 0,
    horarioAtencion: context.horarioAtencion ?? DEFAULT_HORARIO,
    folio: ingreso.uuid,
    observaciones: undefined,
    esMensualidad: ingreso.uuid_subscripcion_cliente !== null,
    sucursal,
  };

  const entradaPayload: EntradaPayload =
    ingreso.placa === null && (ingreso.consecutivo ?? null) !== null
      ? {
          ...base,
          variant: 'con-consecutivo',
          placa: null,
          consecutivo: ingreso.consecutivo as string,
        }
      : {
          ...base,
          variant: 'con-placa',
          placa: ingreso.placa ?? '',
        };

  return {
    originalTipo: 'entrada',
    motivo,
    empresa: DEFAULT_EMPRESA,
    folioOriginal: ingreso.uuid,
    payload: entradaPayload,
  };
}
