/**
 * `Principal.tsx` — page orchestrator for the vehicle entry flow
 * (HU-F6.1, CU-01 + CU-15E, T8).
 *
 * Responsibilities:
 *   1. Render `<TipoIngresoToggle>` (HU-INGRESO-SIN-PLACA, REQ-OPS-195)
 *      with two side-by-side buttons: `Con placa` (default, visually
 *      dominant) + `Sin placa` (outline variant).
 *   2. On valid submit from `<PlacaInput>`, drive `useIngresoActivo`
 *      (T4) to short-circuit the doble-ingreso case (Path 1 filter).
 *   3. On valid submit from `<IngresoSinPlacaPanel>`, post a no-placa
 *      ingreso (`placa_presente: false`) — the discriminated union
 *      variant (REQ-OPS-194).
 *   4. On `201`, auto-print the tiquete via `bridge.imprimir(...)` and
 *      open `<TiqueteModal>` with `consecutivo` for no-placa flows
 *      (REQ-OPS-197).
 *   5. On `422 motivo_forzado_requerido`, open `<ForzarIngresoModal>`
 *      with the previously-typed payload; on confirm, retry POST
 *      with `observaciones: '[FORZADO: ...]'` + `forzado: true`.
 *   6. On `409 ingreso_activo_existente` (the server-authoritative
 *      duplicate path), transparently redirect to the SalidaFlow stub
 *      URL — NO error toast per plan.md line 1530.
 *   7. After each successful submit, the toggle is reset to
 *      `'con-placa'` via a `key="fresh"` remount — the simplest reset
 *      mechanism (avoids lifting toggle state up to the page).
 *
 * DEC-SUC-22 (strict detector, no override), DEC-SUC-21 (server-derived
 * tipo_entrada, never persisted client-side), DEC-SUC-27 (auto-print
 * on 201 + free reprint button per E3 exemption), A-04 (motivo ≥10
 * chars), KD-FORZADO-01 (`[FORZADO:` prefix).
 */
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import { detectarTipoVehiculo } from '../../../lib/validation/placa';
import { useTiposVehiculo } from '../../catalogos/hooks/useTiposVehiculo';

import { ForzarIngresoModal } from '../components/ForzarIngresoModal';
import { IngresoSinPlacaPanel } from '../components/IngresoSinPlacaPanel';
import { PlacaInput } from '../components/PlacaInput';
import { TipoIngresoToggle, type TipoIngresoVariant } from '../components/TipoIngresoToggle';
import { TiqueteModal } from '../components/TiqueteModal';
import { useClienteBySubscripcion } from '../api/clienteApi';
import { buildEntradaPayloadFromResponse } from '../../../lib/print/printBuilder';
import { buildEntradaBuffer } from '../../../lib/print/escposBuilder';
import { useIngresoActivo } from '../hooks/useIngresoActivo';
import {
  type PostIngresoPayload,
  type PostIngresoResponse,
  postIngreso,
} from '../lib/ingresoApi';
import { getIngresoEstado, type Ingreso } from '../api/ingresoActivoApi';

/** SalidaFlow stub URL — Fase 7 will replace with the real screen. */
const SALIDA_FLOW_STUB = '/operacion/salida';

interface SuccessState {
  uuid_ingreso: string;
  tipo_entrada: 'MENSUALIDAD' | 'ROTACION';
  consecutivo: string | null;
  placa: string | null;
  uuid_subscripcion_cliente: string | null;
}

export default function Principal() {
  const { t } = useTranslation('operacion');
  const navigate = useNavigate();
  const tiposVehiculo = useTiposVehiculo();

  const [placa, setPlaca] = useState<string | null>(null);
  const [tipoDetectado, setTipoDetectado] = useState<'carro' | 'moto' | null>(
    null,
  );
  const [observaciones, setObservaciones] = useState<string>('');
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState<SuccessState | null>(null);
  const [forzarOpen, setForzarOpen] = useState(false);
  const [forzarPayload, setForzarPayload] = useState<PostIngresoPayload | null>(
    null,
  );
  const [submitError, setSubmitError] = useState<string | null>(null);
  /**
   * Which toggle variant is currently active. Mirrors the local state
   * inside ``<TipoIngresoToggle>`` (REGRESSION fix 2026-09-22). The
   * parent uses this to hide the global "Registrar ingreso" button +
   * observaciones textarea when the operator switches to "Sin placa"
   * — otherwise both submit CTAs render side-by-side.
   */
  const [activeVariant, setActiveVariant] = useState<TipoIngresoVariant>('con-placa');
  /**
   * Increment on each successful submit so the `<TipoIngresoToggle>`
   * remounts with a fresh `key` — resets its internal state to
   * `'con-placa'` (default). Cheap reset mechanism that avoids
   * lifting state up.
   */
  const [toggleKey, setToggleKey] = useState(0);

  // Path 1: client-side most-recent filter on the GET /ingresos response.
  // Per design.md §Open Questions this may report a false-negative when
  // the most-recent ingreso was already exited; the backend's 409 still
  // wins authoritatively and triggers the transparent redirect.
  const { latestIngreso, refresh: refreshIngresoActivo } =
    useIngresoActivo(placa);

  // Detect tipo when placa changes (uses F4.1 strict detector — no
  // tolerance, NO persisted client-side state).
  useEffect(() => {
    if (!placa) {
      setTipoDetectado(null);
      return;
    }
    setTipoDetectado(detectarTipoVehiculo(placa));
  }, [placa]);

  const handlePlacaSubmit = useCallback(
    async (nextPlaca: string) => {
      setSubmitError(null);
      setPlaca(nextPlaca);

      const tipoNombre = detectarTipoVehiculo(nextPlaca);
      if (tipoNombre === null) {
        // PlacaInput already Zod-validates, so this branch is
        // defensive only.
        setSubmitError('placa_formato_invalido');
        return;
      }

      // Sentinel UUID guard (fix tipo_vehiculo_invalido). When the
      // catalog is degraded (HARDCODED_CATALOG fallback, DEC-F4.1-05),
      // the sentinel UUIDs (00000000-...0001/0002) do NOT exist in
      // prod.tipos_vehiculo. Omit the UUID and let the backend derive
      // it from the placa regex via V5 (operacion.py:184-195).
      let uuid_tipo_vehiculo: string | undefined;
      if (!tiposVehiculo.isFromFallback) {
        const tipoEntry = tiposVehiculo.tipos.find(
          (tv) => tv.tipo === tipoNombre,
        );
        if (!tipoEntry) {
          setSubmitError('cupo_no_configurado');
          return;
        }
        uuid_tipo_vehiculo = tipoEntry.uuid;
      }

      const payload: PostIngresoPayload = {
        placa_presente: true,
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
    [tiposVehiculo.tipos, tiposVehiculo.isFromFallback, observaciones, navigate],
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [forzarPayload, navigate],
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
      // Reset the toggle to the default `'con-placa'` variant by
      // bumping `toggleKey` so the wrapper remounts.
      setToggleKey((k) => k + 1);
      // Auto-print on 201 per DEC-SUC-27 — does NOT block the UI; the
      // IPC call resolves independently. If `bridge.imprimir` rejects
      // (printer offline), the F5.1 retry queue handles it; the
      // operator can also use the always-on Imprimir button in
      // TiqueteModal (E3 exemption).
      try {
        const payload = buildPrintPayload(response, currentPlaca);
        await window.bridge.imprimir(payload);
      } catch {
        // Swallow: ingreso is persisted (DB INSERT is source of truth);
        // F5.1 retry queue drains when the printer reconnects.
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
      // Backend classification — the F1.6 archive wires each 422/409
      // through the dedicated error codes that F6.1 maps to UI actions.
      const body = err.body;
      if (err.status === 409 && body.includes('ingreso_activo_existente')) {
        // Find the active row to thread its uuid to the salida stub.
        // Path 1 simplification: use the cached `latestIngreso` first;
        // fall back to fetching the state directly when the hook's
        // cache is cold (e.g. operator pressed Enter very fast).
        const uuidIngreso = latestIngreso?.uuid ?? (await fetchActiveUuid(placaActual));
        navigate(
          `${SALIDA_FLOW_STUB}?uuid_ingreso=${encodeURIComponent(uuidIngreso)}`,
        );
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

  const handleSiguiente = useCallback(() => {
    setSuccess(null);
    setPlaca(null);
    setTipoDetectado(null);
    setObservaciones('');
    setSubmitError(null);
    void refreshIngresoActivo();
  }, [refreshIngresoActivo]);

  // REGRESSION fix (2026-09-22): SWR-fetched cliente metadata for
  // Mensualidad ingresos, fed into the TiqueteModal preview.
  const { data: clienteData } = useClienteBySubscripcion(
    success?.uuid_subscripcion_cliente,
  );

  return (
    <section className="w-full space-y-6 p-6" aria-labelledby="principal-titulo">
      <header className="space-y-2">
        <h1 id="principal-titulo" className="text-2xl font-semibold">
          {t('ingreso', { defaultValue: 'Ingreso' })}
        </h1>
        <p className="text-sm text-muted-foreground">
          {t('ingreso_subtitulo', {
            defaultValue:
              'Digita la placa del vehículo para registrar el ingreso.',
          })}
        </p>
      </header>

      <TipoIngresoToggle
        key={`toggle-${toggleKey}`}
        onVariantChange={setActiveVariant}
        renderConPlaca={() => (
          <PlacaInput
            onValidSubmit={handlePlacaSubmit}
            disabled={submitting}
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
          observaciones textarea + submit button when con-placa variant
          is active. The sin-placa panel has its OWN submit button
          (inside ``IngresoSinPlacaPanel``). */}
      {activeVariant === 'con-placa' && (
        <>
          <div className="space-y-1">
            <label
              htmlFor="principal-observaciones"
              className="text-sm font-medium"
            >
          {t('ingreso_observaciones_label', { defaultValue: 'Observaciones (opcional)' })}
        </label>
        <textarea
          id="principal-observaciones"
          data-testid="principal-observaciones"
          value={observaciones}
          onChange={(e) => setObservaciones(e.target.value.slice(0, 500))}
          placeholder={t('ingreso_observaciones_placeholder', {
            defaultValue: 'Estado del vehículo, objetos visibles, notas del operador',
          })}
          disabled={submitting}
          maxLength={500}
          rows={2}
          aria-describedby="principal-observaciones-help"
          className="block w-full resize-none rounded border border-input bg-background px-3 py-2 text-sm outline-none ring-ring placeholder:text-muted-foreground focus:ring-2"
        />
        <p
          id="principal-observaciones-help"
          className="text-xs text-muted-foreground"
        >
          {observaciones.length}/500
        </p>
      </div>
        </>
      )}

      {tipoDetectado && (
        <p className="text-sm text-muted-foreground" role="status">
          {t('ingreso_tipo_detectado', {
            defaultValue: 'Tipo detectado',
          })}
          : <strong className="ml-1">{tipoDetectado}</strong>
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
          {t(`error_${submitError}`, {
            defaultValue: submitError,
          })}
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
          initialObservaciones={observaciones}
          buildPrintPayload={(uuid) =>
            buildPrintPayload(
              {
                uuid,
                tipo_entrada: success.tipo_entrada,
                uuid_subscripcion_cliente: success.uuid_subscripcion_cliente,
                consecutivo: success.consecutivo,
              },
              success.placa,
            )
          }
          onSiguiente={handleSiguiente}
          onIrASalida={() => {
            handleSiguiente();
            navigate(
              `${SALIDA_FLOW_STUB}?uuid_ingreso=${encodeURIComponent(success.uuid_ingreso)}`,
            );
          }}
        />
      )}

      {forzarOpen && forzarPayload && forzarPayload.placa_presente && (
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
    </section>
  );
}

/**
 * `buildPrintPayload(response)` — produce the F5.1 IPC payload that
 * wraps the F5.2 ``escposBuilder.buildEntradaBuffer`` result into a
 * base64 buffer + the ingreso UUID as ticketId. F5.2 owns the actual
 * byte composition; F6.1 only wires the result to the bridge.
 *
 * REGRESSION fix (2026-09-22): the prior implementation emitted a
 * sentinel Buffer that ``bridge.imprimir`` rejected — every click on
 * "Imprimir" failed. Now we assemble a structurally valid
 * ``EntradaPayload`` via ``printBuilder.ts`` and serialize through
 * the real F5.2 builder.
 */
function buildPrintPayload(
  response: PostIngresoResponse,
  currentPlaca: string | null,
): { buffer: string; ticketId: string; cut: boolean } {
  const entradaPayload = buildEntradaPayloadFromResponse(
    response,
    response.consecutivo ? null : currentPlaca,
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
  // Fallback when the useIngresoActivo cache is cold: list candidates
  // for the plate and pick the first row whose estado is `abierto`.
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
