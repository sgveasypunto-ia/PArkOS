/**
 * `<IngresoPanel />` — F6.1 dashboard section (REQ-OPS-136, PR-2).
 *
 * Inlined from `pages/Principal.tsx` so the operator registers ingresos
 * without leaving the persistent `/` hub. Composes:
 *
 *   - `<TipoIngresoToggle>` (HU-INGRESO-SIN-PLACA, REQ-OPS-195) wrapping
 *     `<PlacaInput />` (F6.1, RHF + Zod + F4.1 regex) + `<IngresoSinPlacaPanel />`
 *     (REQ-OPS-196).
 *   - `<ForzarIngresoModal />` on 422 `motivo_forzado_requerido`.
 *   - `<TiqueteModal />` on 201 + always-on Imprimir (E3 exemption).
 *   - `useIngresoActivo()` (Path 1 client-side filter for doble-ingreso).
 *
 * `<CotizacionPanel />` (HU-F7.1, PR-3) is wired here when the operator
 * selects an active ingreso — until then, the section issues NO
 * `/cotizar` calls (REQ-OPS-139 cold-Dashboard 0-fetches invariant).
 *
 * 409 `ingreso_activo_existente` → operator is transparently redirected
 * to the SalidaFlow stub URL — exact same flow as `Principal.tsx:53-55`.
 *
 * DEC-SUC-22 (strict detector), DEC-SUC-21 (server-derived tipo_entrada),
 * DEC-SUC-27 (auto-print on 201), A-04 (motivo ≥10 chars),
 * KD-FORZADO-01 (`[FORZADO:` prefix).
 */
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import { detectarTipoVehiculo } from '../../../lib/validation/placa';
import { useTiposVehiculo } from '../../catalogos/hooks/useTiposVehiculo';
import { ForzarIngresoModal } from './ForzarIngresoModal';
import { IngresoSinPlacaPanel } from './IngresoSinPlacaPanel';
import { PlacaInput } from './PlacaInput';
import {
  TipoIngresoToggle,
  type TipoIngresoVariant,
} from './TipoIngresoToggle';
import { TiqueteModal } from './TiqueteModal';
import { useClienteBySubscripcion } from '../api/clienteApi';
import { buildEntradaPayloadFromResponse } from '../../../lib/print/printBuilder';
import { buildEntradaBuffer } from '../../../lib/print/escposBuilder';
import { Button } from '@/components/ui/button';
import { useIngresoActivo } from '../hooks/useIngresoActivo';
import {
  type PostIngresoPayload,
  type PostIngresoResponse,
  postIngreso,
} from '../lib/ingresoApi';
import {
  getIngresoEstado,
  type Ingreso,
} from '../api/ingresoActivoApi';

const SALIDA_FLOW_STUB = '/operacion/salida';

interface SuccessState {
  uuid_ingreso: string;
  tipo_entrada: 'MENSUALIDAD' | 'ROTACION';
  /** REQ-OPS-197: parking-lot identifier for no-placa ingresos. */
  consecutivo: string | null;
  /** REGRESSION fix (2026-09-22): legacy F6.2 placa for con-placa
      ingresos so the tiquete preview can show the right line. Null
      for no-placa ingresos. */
  placa: string | null;
  /** FK to subscripcion_cliente when tipo_entrada === 'MENSUALIDAD';
      triggers the cliente SWR fetch in the modal. */
  uuid_subscripcion_cliente: string | null;
}

export interface IngresoPanelProps {
  /**
   * Optional plate pre-fill. When supplied AND matching the F4.1
   * regexes (Auto | Moto), the panel's `PlacaInput` shows the plate
   * already typed in so the operator only has to press Enter / click
   * "Registrar" once. We DO NOT auto-submit — the operator must
   * confirm. The 409 → /operacion/salida redirect remains the safety
   * net after the manual POST.
   */
  initialPlaca?: string | null;
}

export function IngresoPanel({ initialPlaca = null }: IngresoPanelProps = {}): JSX.Element {
  const { t } = useTranslation('operacion');
  const navigate = useNavigate();
  const tiposVehiculo = useTiposVehiculo();

  const [placa, setPlaca] = useState<string | null>(null);
  const [tipoDetectado, setTipoDetectado] = useState<'carro' | 'moto' | null>(null);
  const [observaciones, setObservaciones] = useState<string>('');
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState<SuccessState | null>(null);
  const [forzarOpen, setForzarOpen] = useState(false);
  const [forzarPayload, setForzarPayload] = useState<PostIngresoPayload | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  /**
   * Which toggle variant is currently active. Mirrors the local state
   * inside `<TipoIngresoToggle>` (REGRESSION fix 2026-09-22: the parent
   * needs this to hide the global "Registrar ingreso" button + the
   * observaciones textarea when the operator switches to "Sin placa" —
   * otherwise both submit CTAs render side-by-side and the operator
   * sees two submit buttons with overlapping intent).
   */
  const [activeVariant, setActiveVariant] = useState<TipoIngresoVariant>('con-placa');
  /**
   * Increment on each successful submit so the `<TipoIngresoToggle>`
   * remounts with a fresh `key` — resets its internal state to
   * `'con-placa'` (default). Cheap reset mechanism that avoids
   * lifting state up.
   */
  const [toggleKey, setToggleKey] = useState(0);

  const { latestIngreso, refresh: refreshIngresoActivo } = useIngresoActivo(placa);
  const tiposVehiculoIsFallback = tiposVehiculo.isFromFallback;

  useEffect(() => {
    if (!placa) {
      setTipoDetectado(null);
      return;
    }
    setTipoDetectado(detectarTipoVehiculo(placa));
  }, [placa]);

  // SWR-fetched cliente metadata for Mensualidad ingresos (REGRESSION
  // fix 2026-09-22). Key is the FK returned by the POST response; SWR
  // dedupes across re-renders.
  const { data: clienteData } = useClienteBySubscripcion(
    success?.uuid_subscripcion_cliente,
  );

  const openSuccessWithAutoPrint = useCallback(
    async (response: PostIngresoResponse, currentPlaca: string | null) => {
      setSuccess({
        uuid_ingreso: response.uuid,
        tipo_entrada: response.tipo_entrada,
        consecutivo: response.consecutivo,
        placa: response.consecutivo ? null : currentPlaca,
        uuid_subscripcion_cliente: response.uuid_subscripcion_cliente,
      });
      setToggleKey((k) => k + 1);
      try {
        const payload = buildPrintPayload(response, currentPlaca);
        await window.bridge.imprimir(payload);
      } catch {
        // Best-effort print — DEC-SUC-27; F5.1 retry queue handles reconnects.
      }
    },
    [],
  );

  /**
   * `handleIngresoSinPlacaSuccess` — the `<IngresoSinPlacaPanel>`
   * success callback. The panel already POSTed with the discriminated
   * no-placa variant; we only need to open the tiquete modal with
   * the response (which carries `consecutivo`).
   */
  const handleIngresoSinPlacaSuccess = useCallback(
    async (response: PostIngresoResponse) => {
      // No-placa flow: pass null placa; the modal uses ``consecutivo``.
      await openSuccessWithAutoPrint(response, null);
    },
    [openSuccessWithAutoPrint],
  );

  const handlePostError = useCallback(
    async (
      err: unknown,
      placaActual: string,
      payload: PostIngresoPayload,
    ): Promise<void> => {
      if (!(err instanceof ParkosHttpError)) {
        setSubmitError('network_error');
        return;
      }
      const body = err.body;
      if (err.status === 409 && body.includes('ingreso_activo_existente')) {
        const uuidIngreso = latestIngreso?.uuid ?? (await fetchActiveUuid(placaActual));
        navigate(`${SALIDA_FLOW_STUB}?uuid_ingreso=${encodeURIComponent(uuidIngreso)}`);
        return;
      }
      if (err.status === 422) {
        if (body.includes('motivo_forzado_requerido')) {
          setForzarPayload(payload);
          setForzarOpen(true);
          return;
        }
        if (body.includes('motivo_forzado_insuficiente')) {
          setSubmitError('motivo_forzado_insuficiente');
          return;
        }
        if (body.includes('cupo_no_configurado')) {
          setSubmitError('cupo_no_configurado');
          return;
        }
        if (body.includes('tarifa_vigente_no_encontrada')) {
          setSubmitError('tarifa_vigente_no_encontrada');
          return;
        }
        if (body.includes('subscripcion_inactiva_o_vencida')) {
          setSubmitError('subscripcion_inactiva_o_vencida');
          return;
        }
      }
      setSubmitError('network_error');
    },
    [latestIngreso, navigate],
  );

  const handlePlacaSubmit = useCallback(
    async (nextPlaca: string) => {
      setSubmitError(null);
      setPlaca(nextPlaca);

      const tipoNombre = detectarTipoVehiculo(nextPlaca);
      if (tipoNombre === null) {
        setSubmitError('placa_formato_invalido');
        return;
      }

      // Sentinel UUID guard (fix tipo_vehiculo_invalido).
      // `tiposVehiculo.tipos` may come from the HARDCODED_CATALOG fallback
      // (DEC-F4.1-05), whose UUIDs (00000000-0000-...0001/0002) do NOT
      // exist in prod.tipos_vehiculo. Sending them triggers V4 in
      // operacion.py:198-205. When the catalog is degraded, omit the
      // UUID and let the backend derive it from the placa regex via the
      // V5 layer (operacion.py:184-195).
      let uuid_tipo_vehiculo: string | undefined;
      if (!tiposVehiculoIsFallback) {
        const tipoEntry = tiposVehiculo.tipos.find((tv) => tv.tipo === tipoNombre);
        if (!tipoEntry) {
          setSubmitError('cupo_no_configurado');
          return;
        }
        uuid_tipo_vehiculo = tipoEntry.uuid;
      }

      const payload: PostIngresoPayload = {
        placa: nextPlaca,
        uuid_tipo_vehiculo,
        observaciones: observaciones.trim() === '' ? undefined : observaciones.trim(),
      };

      setSubmitting(true);
      try {
        const response = await postIngreso(payload);
        await openSuccessWithAutoPrint(response, nextPlaca);
      } catch (err) {
        await handlePostError(err, nextPlaca, payload);
      } finally {
        setSubmitting(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [
      tiposVehiculo.tipos,
      tiposVehiculoIsFallback,
      observaciones,
      navigate,
      openSuccessWithAutoPrint,
      handlePostError,
    ],
  );

  const handleForzarConfirm = useCallback(
    async (forced: { placa: string; motivo: string; observaciones: string }) => {
      if (!forzarPayload) return;
      setForzarOpen(false);
      setSubmitting(true);
      try {
        const response = await postIngreso({
          ...forzarPayload,
          forzado: true,
          observaciones: forced.observaciones,
        });
        await openSuccessWithAutoPrint(response, forced.placa);
      } catch (err) {
        await handlePostError(err, forced.placa, {
          ...forzarPayload,
          forzado: true,
          observaciones: forced.observaciones,
        });
      } finally {
        setSubmitting(false);
        setForzarPayload(null);
      }
    },
    [forzarPayload, openSuccessWithAutoPrint, handlePostError],
  );

  const handleSiguiente = useCallback(() => {
    setSuccess(null);
    setPlaca(null);
    setTipoDetectado(null);
    setObservaciones('');
    setSubmitError(null);
    void refreshIngresoActivo();
  }, [refreshIngresoActivo]);

  return (
    <div
      className="space-y-4"
      data-testid="ingreso-panel"
    >
      <TipoIngresoToggle
        key={`toggle-${toggleKey}`}
        onVariantChange={setActiveVariant}
        renderConPlaca={() => (
          <PlacaInput
            onValidSubmit={handlePlacaSubmit}
            disabled={submitting}
            initialValue={initialPlaca}
            hideSubmitButton
            formId="ingreso-placa-form"
          />
        )}
        renderSinPlaca={() => (
          <IngresoSinPlacaPanel
            onSuccess={handleIngresoSinPlacaSuccess}
            disabled={submitting}
          />
        )}
      />

      {/* REGRESSION fix (2026-09-22): only render the global
          "Observaciones" textarea + "Registrar ingreso" submit button
          when the con-placa variant is active. The sin-placa panel
          has its OWN submit button (inside ``IngresoSinPlacaPanel``)
          so showing both side-by-side would expose two submit CTAs
          with overlapping intent — confusing for the operator. */}
      {activeVariant === 'con-placa' && (
        <>
          <div className="space-y-1">
            <div className="flex items-baseline justify-between">
              <label
                htmlFor="ingreso-observaciones"
                className="text-sm font-medium"
              >
                {t('ingreso_observaciones_label', { defaultValue: 'Observaciones' })}
              </label>
              <span
                className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground"
                data-testid="ingreso-observaciones-badge"
              >
                {t('common:opcional', { defaultValue: 'Opcional' })}
              </span>
            </div>
            <textarea
              id="ingreso-observaciones"
              data-testid="ingreso-observaciones"
              value={observaciones}
              onChange={(e) => setObservaciones(e.target.value.slice(0, 500))}
              placeholder={t('ingreso_observaciones_placeholder', {
                defaultValue: 'Estado del vehículo, objetos visibles, notas del operador',
              })}
              disabled={submitting}
              maxLength={500}
              rows={2}
              aria-describedby="ingreso-observaciones-help"
              className="block w-full resize-none rounded border border-input bg-background px-3 py-2 text-sm outline-none ring-ring placeholder:text-muted-foreground focus:ring-2"
            />
            <p
              id="ingreso-observaciones-help"
              className="text-xs text-muted-foreground"
            >
              {observaciones.length}/500
            </p>
          </div>

          <Button
            type="submit"
            form="ingreso-placa-form"
            disabled={submitting}
            size="lg"
            className="w-full"
            data-testid="ingreso-registrar"
          >
            {t('ingreso_registrar_boton', { defaultValue: 'Registrar ingreso' })}
          </Button>
        </>
      )}

      {tipoDetectado && (
        <p className="text-sm text-muted-foreground" role="status">
          {t('ingreso_tipo_detectado', { defaultValue: 'Tipo detectado' })}:{' '}
          <strong className="ml-1">{tipoDetectado}</strong>
        </p>
      )}

      {latestIngreso && (
        <p
          className="text-sm text-muted-foreground"
          role="status"
          aria-live="polite"
        >
          {t('ingreso_mensualidad_activa', {
            defaultValue: 'Mensualidad activa',
          })}
        </p>
      )}

      {submitError && (
        <p role="alert" className="text-sm text-destructive">
          {t(`error_${submitError}`, { defaultValue: submitError })}
        </p>
      )}

      {success && (
        <TiqueteModal
          open
          uuid_ingreso={success.uuid_ingreso}
          tipo_entrada={success.tipo_entrada}
          consecutivo={success.consecutivo}
          placa={success.placa}
          cliente={
            success.uuid_subscripcion_cliente ? clienteData ?? null : null
          }
          buildPrintPayload={(uuid) =>
            buildPrintPayload({
              uuid_ingreso: uuid,
              tipo_entrada: success.tipo_entrada,
              uuid_subscripcion_cliente: success.uuid_subscripcion_cliente,
              consecutivo: success.consecutivo,
            })
          }
          onSiguiente={handleSiguiente}
        />
      )}

      {forzarOpen && forzarPayload && (
        <ForzarIngresoModal
          open
          placa={forzarPayload.placa}
          onConfirm={handleForzarConfirm}
          onCancel={() => {
            setForzarOpen(false);
            setForzarPayload(null);
          }}
        />
      )}
    </div>
  );
}

/**
 * `buildPrintPayload(response)` — produce the F5.1 IPC payload that
 * wraps the F5.2 ``escposBuilder.buildEntradaBuffer`` result into a
 * base64 buffer + the ingreso UUID as ticketId. F5.2 owns the actual
 * byte composition; this panel only wires the result to the bridge.
 *
 * REGRESSION fix (2026-09-22): the prior implementation emitted a
 * sentinel Buffer (``Buffer.from("tiquete:entrada:...")``) that
 * ``bridge.imprimir`` rejected — every click on "Imprimir" failed
 * with the generic "No se pudo imprimir el tiquete" error. Now we
 * actually call the F5.2 builder via ``printBuilder.ts`` which
 * assembles a structurally valid ``EntradaPayload`` (discriminated
 * union ``con-placa`` | ``con-consecutivo``) before serializing.
 *
 * Note: ``cliente`` is NOT threaded into this payload yet — the
 * tiquete's cliente block is currently rendered only in the preview.
 * Wiring the cliente name into the ESC/POS payload is a follow-up
 * (requires a ``clienteSchema`` to be added to ``escposTemplates.ts``
 * and a 17th/18th key in ``TiqueteEntradaCampos``).
 */
function buildPrintPayload(
  response: PostIngresoResponse,
  currentPlaca: string | null,
): { buffer: string; ticketId: string; cut: boolean } {
  const entradaPayload = buildEntradaPayloadFromResponse(
    response,
    response.consecutivo ? null : currentPlaca,
    // TODO: hydrate from a future GET /print-context endpoint (or
    // individual fetches of empresa + sucursal + tarifa + documentos).
    {},
    null, // cliente metadata not threaded into ESC/POS payload yet
  );
  const buffer = buildEntradaBuffer(entradaPayload);
  return {
    buffer: buffer.toString('base64'),
    ticketId: response.uuid,
    cut: true,
  };
}

async function fetchActiveUuid(placaTarget: string): Promise<string> {
  try {
    const { getIngresosByPlaca } = await import('../api/ingresoActivoApi');
    const rows: Ingreso[] = await getIngresosByPlaca(placaTarget);
    for (const row of rows) {
      const estado = await getIngresoEstado(row.uuid);
      if (estado.estado === 'abierto') {
        return row.uuid;
      }
    }
    return rows[0]?.uuid ?? '';
  } catch {
    return '';
  }
}