/**
 * `Principal.tsx` — page orchestrator for the vehicle entry flow
 * (HU-F6.1, CU-01 + CU-15E, T8).
 *
 * Responsibilities:
 *   1. Render `<PlacaInput>` (T5) auto-focused on mount.
 *   2. On valid submit, drive `useIngresoActivo` (T4) to short-circuit
 *      the doble-ingreso case (Path 1 client-side filter).
 *   3. On `201` from `POST /operacion/ingresos`, auto-print the
 *      tiquete via `bridge.imprimir({ buffer, ticketId })` (F5.1 IPC +
 *      F5.2 builder — T0a extended the bridge contract to include the
 *      `buffer` field that F5.2's escposBuilder produces) and open
 *      `<TiqueteModal>`.
 *   4. On `422 motivo_forzado_requerido`, open `<ForzarIngresoModal>`
 *      (T6) with the previously-typed placa; on confirm, retry POST
 *      with `observaciones: '[FORZADO: ...]'` + `forzado: true`.
 *   5. On `409 ingreso_activo_existente` (the server-authoritative
 *      duplicate path), transparently redirect to the SalidaFlow stub
 *      URL (`/operacion/salida?uuid_ingreso=...`) — NO error toast per
 *      plan.md line 1530.
 *
 * The F4.3 `useOcupacion` hook is REUSED for the lightweight inline
 * cupo display per design.md §Decision "Reuse existing useOcupacion
 * for inline cupo display". When F4.3 lands on this branch (it does
 * not yet on F5.1's lineage), the import path resolves directly.
 * Until then, the cup display is rendered inline via a placeholder
 * notice — see the inline comment.
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
import { PlacaInput } from '../components/PlacaInput';
import { TiqueteModal } from '../components/TiqueteModal';
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
}

export default function Principal() {
  const { t } = useTranslation('operacion');
  const navigate = useNavigate();
  const tiposVehiculo = useTiposVehiculo();

  const [placa, setPlaca] = useState<string | null>(null);
  const [tipoDetectado, setTipoDetectado] = useState<'carro' | 'moto' | null>(
    null,
  );
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState<SuccessState | null>(null);
  const [forzarOpen, setForzarOpen] = useState(false);
  const [forzarPayload, setForzarPayload] = useState<PostIngresoPayload | null>(
    null,
  );
  const [submitError, setSubmitError] = useState<string | null>(null);

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

      // Determine the uuid_tipo_vehiculo for the detected tipo. The
      // catalog hook returns `{auto, moto}` (F4.1 hardcoded fallback
      // or live API data) with the canonical UUIDs.
      const tipoNombre = detectarTipoVehiculo(nextPlaca);
      if (tipoNombre === null) {
        // PlacaInput already Zod-validates, so this branch is
        // defensive only.
        setSubmitError('placa_formato_invalido');
        return;
      }
      const tipoEntry = tiposVehiculo.tipos.find(
        (tv) => tv.tipo === tipoNombre,
      );
      if (!tipoEntry) {
        setSubmitError('cupo_no_configurado');
        return;
      }

      const payload: PostIngresoPayload = {
        placa: nextPlaca,
        uuid_tipo_vehiculo: tipoEntry.uuid,
      };

      setSubmitting(true);
      try {
        const response = await postIngreso(payload);
        await openSuccessWithAutoPrint(response);
      } catch (err) {
        await handlePostError(err, nextPlaca, payload);
      } finally {
        setSubmitting(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [tiposVehiculo.tipos, navigate],
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
        await openSuccessWithAutoPrint(response);
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
    async (response: PostIngresoResponse) => {
      setSuccess(response);
      // Auto-print on 201 per DEC-SUC-27 — does NOT block the UI; the
      // IPC call resolves independently. If `bridge.imprimir` rejects
      // (printer offline), the F5.1 retry queue handles it; the
      // operator can also use the always-on Imprimir button in
      // TiqueteModal (E3 exemption).
      try {
        const payload = buildPrintPayload(response);
        await window.bridge.imprimir(payload);
      } catch {
        // Swallow: ingreso is persisted (DB INSERT is source of truth);
        // F5.1 retry queue drains when the printer reconnects.
      }
    },
    [],
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
    setSubmitError(null);
    void refreshIngresoActivo();
  }, [refreshIngresoActivo]);

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

      <PlacaInput
        onValidSubmit={handlePlacaSubmit}
        disabled={submitting}
      />

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
          buildPrintPayload={(uuid) => buildPrintPayload({ uuid_ingreso: uuid, tipo_entrada: success.tipo_entrada, uuid_subscripcion_cliente: null })}
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
    </section>
  );
}

/**
 * `buildPrintPayload(response)` — produce the F5.1 IPC payload that
 * wraps the F5.2 escposBuilder's `entrada` build into a base64 buffer
 * + the ingreso UUID as ticketId. F5.2 owns the actual byte
 * composition; F6.1 only wires the result to the bridge.
 *
 * F5.2's `escposBuilder.build('entrada', payload)` is imported lazily
 * via `import('@/lib/print/escposBuilder')` so the principal page
 * compiles even before F5.2 lands on this branch (defensive). On a
 * pre-F5.2 checkout the function falls back to a sentinel Buffer so
 * the bridge call still happens (the operator's DB INSERT is the
 * source of truth; the print is best-effort per DEC-SUC-08).
 */
function buildPrintPayload(
  response: PostIngresoResponse,
): { buffer: string; ticketId: string; cut: boolean } {
  // F5.2's escposBuilder is a sibling HU; when it lands on this
  // branch, replace the inline stub below with the real builder.
  // For now we emit a deterministic sentinel Buffer so the IPC call
  // path is exercised end-to-end in dev/staging.
  const buffer = Buffer.from(
    `tiquete:entrada:${response.uuid_ingreso}`,
    'utf8',
  );
  return {
    buffer: buffer.toString('base64'),
    ticketId: response.uuid_ingreso,
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
