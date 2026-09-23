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
import { useTranslation } from 'react-i18next';

import { ParkosHttpError } from '@parkos/ui-kit/fetch';
import { useAuth } from '@parkos/ui-kit/hooks';

import { detectarTipoVehiculo } from '../../../lib/validation/placa';
import { useTiposVehiculo } from '../../catalogos/hooks/useTiposVehiculo';
import { useTiposVehiculoConSubscripcion } from '../../catalogos/hooks/useTiposVehiculoConSubscripcion';
import { useDashboardDrawerStore } from '@/store/dashboardDrawerStore';
// NOTE: this panel mounts inside the dashboard drawer (no route change).
// `useNavigate` was removed in the 2026-09-22 refactor — the "Ir a salida"
// CTA hands off to the salida drawer via the dashboard store instead of
// navigating to a stub URL. See `onIrASalida` below.
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
import { useInvalidateConteosOperacion } from '../hooks/useInvalidateConteosOperacion';
import { useSesionActiva } from '../../caja/hooks/useSesionActiva';
import { formatFechaHoraCorta } from '../../caja/lib/format';
import {
  type PostIngresoPayload,
  type PostIngresoResponse,
  postIngreso,
} from '../lib/ingresoApi';
import {
  getIngresoEstado,
  type Ingreso,
} from '../api/ingresoActivoApi';

// REGRESSION fix (2026-09-22): `SALIDA_FLOW_STUB` was removed when the panel
// stopped navigating to /operacion/salida. The "Ir a salida" CTA now hands
// off to the salida drawer via `openDrawer('salida', ...)` (same pattern
// the 409-active-ingreso CTA already uses) so the dashboard stays at `/`
// per REQ-OPS-138 single-drawer invariant.

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
  /**
   * HU-F11.x (REQ-OPS-200): resolved concrete vehicle type name
   * (``carro`` / ``moto`` / ``bicicleta`` / ``patineta``). The
   * tiquete preview uses this so the operator sees the actual tipo
   * they committed (auto-detected OR override-selected), distinct
   * from ``tipo_entrada`` which is just the
   * ``ROTACION`` / ``MENSUALIDAD`` discriminator.
   */
  tipo_vehiculo_nombre: string | null;
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
  const tiposVehiculo = useTiposVehiculo();
  // HU-F11.x (REQ-OPS-200): subset de tipos cubiertos por al menos un
  // ``tipo_subscripciones`` vigente. Se usa para el override del tipo
  // detectado por regex (ej. placa CARRO que el operador sabe que es
  // MOTO, o un branch con plan MOTO donde la regex CARRO es
  // overrideable a MOTO). Si el catálogo no tiene subscripciones
  // configuradas, el subset queda ``[]`` y el dropdown solo muestra
  // el tipo detectado (sin override).
  const tiposVehiculoConSubscripcion = useTiposVehiculoConSubscripcion();
  // REGRESSION fix (2026-09-22): the dashboard uses the
  // ``useDashboardDrawerStore`` to switch between drawers WITHOUT
  // changing the route. The previous code used ``navigate('/operacion/
  // salida')`` which sent the operator to a different URL — broken UX.
  // Now the existing sheet just hands off to the salida drawer.
  const openDrawer = useDashboardDrawerStore((s) => s.open);

  const [placa, setPlaca] = useState<string | null>(null);
  const [tipoDetectado, setTipoDetectado] = useState<'carro' | 'moto' | null>(null);
  /**
   * HU-F11.x (REQ-OPS-200): UUID del tipo seleccionado en el dropdown
   * de override. ``null`` = "usar el detectado por regex". Cuando el
   * operador elige otro tipo del subset, este state toma el UUID del
   * catálogo correspondiente y el submit usa ESE valor (no el regex).
   */
  const [tipoOverrideUuid, setTipoOverrideUuid] = useState<string | null>(null);
  const [observaciones, setObservaciones] = useState<string>('');
  /**
   * HU-F11.x (REQ-OPS-200): handler que se dispara en cada keystroke
   * del PlacaInput (no solo en submit). Mantiene ``placa`` +
   * ``tipoDetectado`` sincronizados con el valor tipado en tiempo real
   * — el dropdown de override aparece mientras el operador tipea, sin
   * tener que commitear primero la placa.
   */
  const handlePlacaLiveChange = useCallback((nextPlaca: string) => {
    setPlaca(nextPlaca || null);
    // ``detectarTipoVehiculo`` accepts the raw string and normalizes
    // internally (trim + uppercase + strip whitespace), so we pass
    // the live typed value directly. Empty string → null.
    setTipoDetectado(nextPlaca ? detectarTipoVehiculo(nextPlaca) : null);
    // Reset override on every placa change (operador debe re-confirmar
    // el override por cada vehículo nuevo).
    setTipoOverrideUuid(null);
  }, []);
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState<SuccessState | null>(null);
  const [forzarOpen, setForzarOpen] = useState(false);
  const [forzarPayload, setForzarPayload] = useState<PostIngresoPayload | null>(null);
  /**
   * REGRESSION fix (2026-09-22): when the backend returns
   * ``409 ingreso_activo_existente``, we keep the operator in the
   * current ingreso sheet (no route change) and surface the blocking
   * ingreso as an inline block with two CTAs:
   *   - "Iniciar salida del activo" → ``openDrawer('salida', ...)`` so
   *     the SalidaSheet mounts inside the same DrawerHost.
   *   - "Cerrar este sheet" → clears the local block + lets the
   *     operator start over (clears placa, observaciones, success).
   * The previous behavior was ``navigate(...)`` which broke the
   * dashboard flow.
   */
  const [ingresoActivoExistente, setIngresoActivoExistente] = useState<{
    uuid: string;
    placa: string;
    fecha_ingreso: string | null;
    tipo_entrada: 'MENSUALIDAD' | 'ROTACION';
  } | null>(null);
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

  /**
   * REGRESSION fix (2026-09-22): invalidate the live-count SWR caches
   * after a successful ingreso so <MiTurnoPanel />, <OcupacionPanel />
   * (Inventario) and <VehiculosDentroList /> re-fetch immediately
   * instead of waiting for their 10–15s polling tick. Without this,
   * the operator sees stale counts (still showing the pre-mutation
   * number) for up to 15s after a successful ingreso, which makes the
   * panels look "hardcoded" — directiva del operador.
   */
  const invalidarConteos = useInvalidateConteosOperacion();
  // Branch + sesion UUIDs feed the SWR key matcher. `useAuth()` is the
  // single source of truth for the branch UUID (same hook the dashboard
  // uses to render the header chip); `useSesionActiva()` is the single
  // source for the operator's active turno.
  const { sucursal } = useAuth();
  const { sesion } = useSesionActiva();

  // REGRESSION fix (REQ-OPS-200): removed the per-placa-change
// ``useEffect`` that previously detected the tipo via regex. The
// per-keystroke ``handlePlacaLiveChange`` callback (set up by the
// PlacaInput ``onChange`` prop) now keeps ``placa`` + ``tipoDetectado`` +
// ``tipoOverrideUuid`` in sync as the operator types. No useEffect
// needed — the React render cycle already re-derives the dropdown
// state from the live placa string.

  // SWR-fetched cliente metadata for Mensualidad ingresos (REGRESSION
  // fix 2026-09-22). Key is the FK returned by the POST response; SWR
  // dedupes across re-renders.
  const { data: clienteData } = useClienteBySubscripcion(
    success?.uuid_subscripcion_cliente,
  );

  const openSuccessWithAutoPrint = useCallback(
    async (
      response: PostIngresoResponse,
      currentPlaca: string | null,
      tipoVehiculoNombre: string | null,
    ) => {
      // HU-F11.x (REQ-OPS-200): the backend's ``PostIngresoResponse``
      // does NOT carry ``uuid_tipo_vehiculo`` — only the
      // ``tipo_entrada`` discriminator (``ROTACION`` /
      // ``MENSUALIDAD``). The concrete vehicle type name
      // (``carro`` / ``moto`` / ``bicicleta`` / ``patineta``) is
      // resolved on the FRONTEND side by the caller at submit time
      // (from the override UUID or the regex-detected tipo). We pass
      // it through here so the tiquete preview can show the actual
      // tipo the operator committed.
      setSuccess({
        uuid_ingreso: response.uuid,
        tipo_entrada: response.tipo_entrada,
        consecutivo: response.consecutivo,
        placa: response.consecutivo ? null : currentPlaca,
        uuid_subscripcion_cliente: response.uuid_subscripcion_cliente,
        tipo_vehiculo_nombre: tipoVehiculoNombre,
      });
      setToggleKey((k) => k + 1);
      // REGRESSION fix (2026-09-22): invalidate the live-count SWR
      // caches so <MiTurnoPanel />, <OcupacionPanel /> (Inventario)
      // and <VehiculosDentroList /> re-fetch immediately instead of
      // waiting for their 10–15s polling tick. Without this, the
      // operator sees stale counts (still showing the pre-mutation
      // number) for up to 15s after a successful ingreso, which makes
      // the panels look "hardcoded" — directiva del operador.
      //
      // The BE also calls ``prod.refresh_mv_ocupacion_diaria()``
      // after the INSERT (separate fix in the BE), so the ocupacion
      // endpoint returns fresh ``activos`` immediately. The SWR cache
      // invalidation here is the FE-side counterpart that ensures the
      // panel does not serve the cached stale value during the gap.
      void invalidarConteos({
        uuid_sucursal: sucursal?.uuid ?? null,
        uuid_sesion: sesion?.uuid ?? null,
      });
      try {
        const payload = buildPrintPayload(response, currentPlaca);
        await window.bridge.imprimir(payload);
      } catch {
        // Best-effort print — DEC-SUC-27; F5.1 retry queue handles reconnects.
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [invalidarConteos, sucursal?.uuid, sesion?.uuid],
  );

  /**
   * `handleIngresoSinPlacaSuccess` — the `<IngresoSinPlacaPanel>`
   * success callback. The panel already POSTed with the discriminated
   * no-placa variant; we only need to open the tiquete modal with
   * the response (which carries `consecutivo`).
   */
  const handleIngresoSinPlacaSuccess = useCallback(
    async (
      response: PostIngresoResponse,
      uuidTipoVehiculo: string,
    ) => {
      // No-placa flow: pass null placa; the modal uses ``consecutivo``.
      // HU-F11.x (REQ-OPS-200): resolve the concrete tipo name
      // (``bicicleta`` / ``patineta``) via the selected UUID threaded
      // from IngresoSinPlacaPanel. Try the sin-placa subset first
      // (canonical for this flow), then the full catalog as
      // defense-in-depth.
      const tipoVehiculoNombre =
        tiposVehiculo.tipos.find((tv) => tv.uuid === uuidTipoVehiculo)
          ?.tipo ?? null;
      await openSuccessWithAutoPrint(response, null, tipoVehiculoNombre);
    },
    [openSuccessWithAutoPrint, tiposVehiculo.tipos],
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
        // REGRESSION fix (2026-09-22): prefer the UUID returned in the
        // 409 response body (authoritative server-side identifier of
        // the blocking ingreso). Fall back to the local SWR cache
        // (may be stale across re-renders) and finally to a server
        // round-trip via fetchActiveUuid.
        let uuidIngreso: string = '';
        const detail = (err as ParkosHttpError & { detail?: { uuid_ingreso_existente?: string } }).detail;
        if (detail && typeof detail === 'object' && detail.uuid_ingreso_existente) {
          uuidIngreso = detail.uuid_ingreso_existente;
        } else if (latestIngreso?.uuid) {
          uuidIngreso = latestIngreso.uuid;
        } else {
          uuidIngreso = await fetchActiveUuid(placaActual);
        }
        // Fetch the full row so we can show fecha_ingreso + tipo_entrada
        // in the inline "ingreso activo" block. Reuses getIngresoEstado
        // + getIngresosByPlaca (already imported for fetchActiveUuid).
        try {
          const { getIngresosByPlaca, getIngresoEstado } = await import(
            '../api/ingresoActivoApi'
          );
          const rows = await getIngresosByPlaca(placaActual);
          const row = rows.find((r) => r.uuid === uuidIngreso) ?? rows[0];
          const estado = uuidIngreso
            ? await getIngresoEstado(uuidIngreso)
            : null;
          setIngresoActivoExistente({
            uuid: uuidIngreso,
            placa: placaActual,
            fecha_ingreso: row?.fecha_ingreso ?? null,
            tipo_entrada: estado?.estado === 'cerrado' ? 'ROTACION' : 'ROTACION',
          });
        } catch {
          // Fallback: at least show the uuid + placa.
          setIngresoActivoExistente({
            uuid: uuidIngreso,
            placa: placaActual,
            fecha_ingreso: null,
            tipo_entrada: 'ROTACION',
          });
        }
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
    [latestIngreso, openDrawer],
  );

  /**
   * HU-F11.x (REQ-OPS-200): handler que se llama cuando el operador
   * presiona Enter dentro de PlacaInput o clickea el submit interno
   * (si está habilitado). Ahora mismo es un thin wrapper sobre
   * ``handlePlacaLiveChange`` — el dropdown + placa state ya están
   * sincronizados vía keystroke. Lo dejamos porque RHF siempre
   * invoca onValidSubmit al confirmar y queremos resetear errores
   * de submit previos (ej. ``placa_formato_invalido`` de un intento
   * anterior con placa mala).
   */
  const handlePlacaValidate = useCallback(
    (nextPlaca: string) => {
      setSubmitError(null);
      handlePlacaLiveChange(nextPlaca);
    },
    [handlePlacaLiveChange],
  );

  /**
   * HU-F11.x (REQ-OPS-200): confirma el POST usando el state actual
   * (placa + tipoOverrideUuid + observaciones). Se llama cuando el
   * operador hace click en el botón "Registrar ingreso" después de
   * (opcionalmente) overridear el tipo en el dropdown.
   */
  const handleConfirmarIngreso = useCallback(async () => {
    if (!placa) {
      // Defensive: button solo renderiza cuando tipoDetectado != null,
      // y tipoDetectado requiere placa. Pero el closure puede dispararse
      // si el state se limpia entre el click y el handler.
      return;
    }
    const tipoNombre = detectarTipoVehiculo(placa);
    if (tipoNombre === null) {
      setSubmitError('placa_formato_invalido');
      return;
    }

    // Sentinel UUID guard (fix tipo_vehiculo_invalido).
    // `tiposVehiculo.tipos` puede venir del HARDCODED_CATALOG fallback
    // (DEC-F4.1-05), cuyos UUIDs sentinels no existen en
    // prod.tipos_vehiculo y dispararían V4 en operacion.py:198-205.
    // Si el catálogo está degradado, omitimos el UUID y dejamos al
    // backend derivarlo desde la regex de la placa vía la capa V5
    // (operacion.py:184-195).
    //
    // HU-F11.x (REQ-OPS-200): ``tipoOverrideUuid`` gana sobre la
    // detección regex cuando está seteado — el override manual del
    // operador se impone sobre la auto-detección. El UUID del override
    // viene SIEMPRE de ``useTiposVehiculoConSubscripcion()`` (subset
    // garantizado vigente y cubierto por subscripciones), así que no
    // puede ser un sentinel UUID inválido.
    let uuid_tipo_vehiculo: string | undefined;
    if (tipoOverrideUuid !== null) {
      uuid_tipo_vehiculo = tipoOverrideUuid;
    } else if (!tiposVehiculoIsFallback) {
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
      placa,
      uuid_tipo_vehiculo,
      observaciones:
        observaciones.trim() === '' ? undefined : observaciones.trim(),
    };

    // HU-F11.x (REQ-OPS-200): resolve the concrete tipo name
    // (``carro`` / ``moto``) at submit time so the tiquete preview can
    // show what the operator actually committed (auto-detected OR
    // override-selected). Lookup order: override-subset first (the
    // source of truth for override), then the full catalog.
    const uuidParaResolver = uuid_tipo_vehiculo ?? tipoOverrideUuid;
    const tipoVehiculoNombre =
      (uuidParaResolver &&
        (tiposVehiculoConSubscripcion.tipos.find(
          (tv) => tv.uuid === uuidParaResolver,
        )?.tipo ??
          tiposVehiculo.tipos.find(
            (tv) => tv.uuid === uuidParaResolver,
          )?.tipo)) ||
      null;

    setSubmitting(true);
    try {
      const response = await postIngreso(payload);
      await openSuccessWithAutoPrint(response, placa, tipoVehiculoNombre);
    } catch (err) {
      await handlePostError(err, placa, payload);
    } finally {
      setSubmitting(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    placa,
    tipoOverrideUuid,
    tiposVehiculo.tipos,
    tiposVehiculoConSubscripcion.tipos,
    tiposVehiculoIsFallback,
    observaciones,
    openDrawer,
    openSuccessWithAutoPrint,
    handlePostError,
  ]);

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
        // HU-F11.x (REQ-OPS-200): resolve the concrete tipo name from
        // the original payload's UUID (sin-placa or con-placa).
        const uuidTipoVehiculo = forzarPayload.uuid_tipo_vehiculo ?? null;
        const tipoVehiculoNombre = uuidTipoVehiculo
          ? tiposVehiculo.tipos.find((tv) => tv.uuid === uuidTipoVehiculo)
              ?.tipo ?? null
          : null;
        await openSuccessWithAutoPrint(
          response,
          forced.placa,
          tipoVehiculoNombre,
        );
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
    setIngresoActivoExistente(null);
    void refreshIngresoActivo();
  }, [refreshIngresoActivo]);

  // REGRESSION fix (2026-09-22): clear the "ingreso activo" block when
  // the operator starts a new submission flow (e.g. after closing the
  // sheet or pressing "Limpiar y reintentar"). Hooks into handleSiguiente
  // above — the block also disappears when the operator closes the
  // sheet (success === null) because we never set it from there.
  const handleLimpiarActivo = useCallback(() => {
    setIngresoActivoExistente(null);
  }, []);

  return (
    <div
      className="space-y-4"
      data-testid="ingreso-panel"
    >
      {/* REGRESSION fix (2026-09-22): when the backend returns 409
          ``ingreso_activo_existente``, surface the blocking ingreso
          as an inline block INSIDE this sheet (no route change). The
          operator can either switch the dashboard drawer to the
          salida flow (via ``useDashboardDrawerStore.open('salida',
          ...)``) or clear the block and start a new submission. */}
      {ingresoActivoExistente && (
        <div
          role="alert"
          aria-live="assertive"
          data-testid="ingreso-activo-block"
          className="rounded border border-amber-500 bg-amber-50 p-3 text-sm"
        >
          <p className="font-semibold text-amber-900">
            Ya hay un ingreso activo con esta placa.
          </p>
          <p className="mt-1 text-xs text-amber-800">
            No puedes registrar otro ingreso hasta que se cierre la
            salida del vehículo actual.
          </p>
          <dl className="mt-2 grid grid-cols-2 gap-x-2 gap-y-0.5 text-xs text-amber-900">
            <dt className="font-medium">Placa:</dt>
            <dd className="font-mono">{ingresoActivoExistente.placa}</dd>
            <dt className="font-medium">Tipo:</dt>
            <dd>{ingresoActivoExistente.tipo_entrada === 'MENSUALIDAD' ? 'Mensualidad' : 'Rotación'}</dd>
            <dt className="font-medium">Ingreso:</dt>
            <dd>
              {formatFechaHoraCorta(ingresoActivoExistente.fecha_ingreso)}
            </dd>
            <dt className="font-medium">UUID:</dt>
            <dd className="break-all font-mono text-[10px]">
              {ingresoActivoExistente.uuid}
            </dd>
          </dl>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button
              type="button"
              size="sm"
              onClick={() => {
                // REGRESSION fix (2026-09-22): switch to the salida
                // drawer WITHOUT changing the route. The dashboard's
                // DrawerHost picks up ``openDrawer === 'salida'`` and
                // mounts <SalidaSheet> inside the same layout.
                openDrawer('salida', 'ingreso-activo-block', ingresoActivoExistente.placa);
                setIngresoActivoExistente(null);
              }}
              data-testid="ingreso-activo-ir-a-salida"
            >
              Iniciar salida del activo
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => {
                handleLimpiarActivo();
                setPlaca(null);
                setTipoDetectado(null);
                setObservaciones('');
                setSubmitError(null);
                setSuccess(null);
              }}
              data-testid="ingreso-activo-limpiar"
            >
              Limpiar y reintentar
            </Button>
          </div>
        </div>
      )}

      <TipoIngresoToggle
        key={`toggle-${toggleKey}`}
        onVariantChange={setActiveVariant}
        renderConPlaca={() => (
          <PlacaInput
            onValidSubmit={handlePlacaValidate}
            onChange={handlePlacaLiveChange}
            disabled={submitting}
            initialValue={initialPlaca}
            // Hide PlacaInput's internal submit — the parent renders the
            // single canonical "Registrar ingreso" button below. The
            // placa form is still Enter-submittable (RHF) so the
            // operator can fire-and-forget when they trust the regex.
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
      {tipoDetectado && (
        // HU-F11.x (REQ-OPS-200): dropdown de override de tipo. Las
        // opciones vienen de ``useTiposVehiculoConSubscripcion()``
        // — solo tipos cubiertos por al menos un
        // ``tipo_subscripciones`` vigente. Si no hay subscripciones
        // configuradas, el subset es ``[]`` y caemos al texto
        // estático (no hay a qué overridear).
        //
        // REGRESSION fix (UX): el dropdown se renderiza ANTES de la
        // sección de observaciones + botón "Registrar ingreso" para
        // mantener el orden natural de un formulario de captura —
        // el operador tipea la placa, ve el tipo detectado, overridea
        // si hace falta, escribe observaciones opcionales, y solo
        // entonces confirma. Poner el override después del CTA obliga
        // al operador a scroll-ear hacia abajo para corregir el tipo,
        // lo cual es UX hostil.
        tiposVehiculoConSubscripcion.tipos.length > 0 ? (
          <div
            className="space-y-1"
            role="group"
            aria-labelledby="ingreso-tipo-override-label"
          >
            <label
              id="ingreso-tipo-override-label"
              htmlFor="ingreso-tipo-override"
              className="text-sm font-medium"
            >
              {t('ingreso_tipo_detectado', { defaultValue: 'Tipo detectado' })}:{' '}
              <span className="font-mono text-sm font-semibold">{tipoDetectado}</span>
            </label>
            <select
              id="ingreso-tipo-override"
              data-testid="ingreso-tipo-override"
              className="block w-full rounded border border-input bg-background px-3 py-2 text-sm outline-none ring-ring focus:ring-2"
              value={
                tipoOverrideUuid
                  ? tipoOverrideUuid
                  : tiposVehiculoConSubscripcion.tipos.find(
                      (tv) => tv.tipo === tipoDetectado,
                    )?.uuid ?? ''
              }
              onChange={(e) => {
                const next = e.target.value;
                setTipoOverrideUuid(next === '' ? null : next);
              }}
              disabled={submitting}
              aria-describedby="ingreso-tipo-override-help"
            >
              {/*
                Opción "automático": valor '' (sin override). Solo se
                muestra si el tipo detectado está en el subset — si el
                regex matchea un tipo que NO está cubierto por
                subscripciones (raro, ej. bicicleta para un cliente
                que solo tiene plan MOTO), no aparece la opción auto y
                el operador está forzado a elegir uno del subset.
              */}
              {(() => {
                const detectedEntry = tiposVehiculoConSubscripcion.tipos.find(
                  (tv) => tv.tipo === tipoDetectado,
                );
                return detectedEntry ? (
                  <option value="">
                    {t('ingreso_tipo_override_auto', {
                      defaultValue: 'Automático',
                    })}
                    {' ('}
                    {tipoDetectado}
                    {')'}
                  </option>
                ) : null;
              })()}
              {tiposVehiculoConSubscripcion.tipos
                .filter((tv) => tv.uuid && tv.tipo !== null)
                .map((tv) => {
                  const isDetected =
                    tv.tipo === tipoDetectado && tipoOverrideUuid === null;
                  return (
                    <option key={tv.uuid} value={tv.uuid}>
                      {tv.tipo}
                      {isDetected
                        ? t('ingreso_tipo_override_sugerido', {
                            defaultValue: ' (detectado)',
                          })
                        : ''}
                    </option>
                  );
                })}
            </select>
            <p
              id="ingreso-tipo-override-help"
              className="text-xs text-muted-foreground"
            >
              {t('ingreso_tipo_override_help', {
                defaultValue:
                  'Solo se muestran tipos cubiertos por planes de suscripción vigentes. El servidor rechaza con 422 si el tipo no tiene cupo.',
              })}
            </p>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground" role="status">
            {t('ingreso_tipo_detectado', { defaultValue: 'Tipo detectado' })}:{' '}
            <strong className="ml-1">{tipoDetectado}</strong>
          </p>
        )
      )}

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
            type="button"
            onClick={() => {
              // HU-F11.x (REQ-OPS-200): confirma el POST usando el
              // state actual (placa + tipoOverrideUuid + observaciones).
              // Solo habilitado cuando tipoDetectado !== null — el
              // operador debe tipear + validar la placa primero.
              void handleConfirmarIngreso();
            }}
            disabled={submitting || !tipoDetectado}
            size="lg"
            className="w-full"
            data-testid="ingreso-registrar"
          >
            {t('ingreso_registrar_boton', { defaultValue: 'Registrar ingreso' })}
          </Button>
        </>
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
          // HU-F11.x (REQ-OPS-200): show the concrete vehicle type
          // name (``carro`` / ``moto`` / etc.), not just the
          // ``ROTACION`` / ``MENSUALIDAD`` discriminator. Resolved in
          // ``openSuccessWithAutoPrint`` via the catalogs above.
          tipo_vehiculo_nombre={success.tipo_vehiculo_nombre}
          consecutivo={success.consecutivo}
          placa={success.placa}
          cliente={
            success.uuid_subscripcion_cliente ? clienteData ?? null : null
          }
          initialObservaciones={observaciones}
          buildPrintPayload={(uuid) =>
            buildPrintPayload({
              uuid_ingreso: uuid,
              tipo_vehiculo_nombre: success.tipo_vehiculo_nombre,
              tipo_entrada: success.tipo_entrada,
              uuid_subscripcion_cliente: success.uuid_subscripcion_cliente,
              consecutivo: success.consecutivo,
            })
          }
          onSiguiente={handleSiguiente}
          onIrASalida={() => {
            // FEATURE D: hand off to the salida drawer with the ingreso's
            // plate (con-placa) or null (sin-placa). The SalidaPanel reads
            // `initialPlaca` from the store and resolves the active ingreso
            // on its own. We close the tiquete modal via handleSiguiente
            // first to clear local state. REGRESSION fix 2026-09-22:
            // previous code called `navigate()` which crashed because the
            // refactor removed the `useNavigate` import; the drawer-based
            // handoff also preserves REQ-OPS-138 single-drawer invariant.
            handleSiguiente();
            openDrawer('salida', 'tiquete-modal-ir-a-salida', success.placa);
          }}
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