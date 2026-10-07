/**
 * `<CerrarTurno />` — container orchestrator (HU-F10.2).
 *
 * Chaines the F10.1 substrate (`useArqueo().submit({ tipo_arqueo:
 * 'cierre_turno' })`) with the F3.3 sesion-close helper
 * (`useSesionActiva().cerrarSesion(uuid, payload)`) on a single
 * confirmation (REQ-OPS-157 + AD-2 + AD-3).
 *
 * The 3-step sequencer is implemented in `./cerrarTurnoChain.ts` as
 * a pure helper for unit-testability. The orchestrator wires the
 * helper's `CerrarTurnoChainResult` to the UI banners + `navigate(...)`
 * calls.
 *
 * Predecessors: F3.3 DEC-F3.3-03 + DEC-F3.3-06 + DEC-F3.3-07; F10.1
 * ArqueoParcial page (REQ-OPS-152..156). The F3.3 logout-on-success
 * trifecta (`useAuthStore.clear()` + `parkos:auth:cleared` event +
 * `navigate('/login?closed=true')`) is preserved per Engram #1899 (Q1
 * ratified 2026-09-21), but PT-5 DEFERS it: after the PUT succeeds the
 * operator first sees a read-only summary (`<ResumenCierreTurno>`), and the
 * trifecta runs when they press "Finalizar y salir" — or, as a safety net,
 * when this component unmounts while the summary is pending (Esc / drawer
 * dismissed), so a closed turn can never leave a logged-in operator behind.
 *
 * 8-case error precedence (AD-3, exhaustive against `prod.arqueo [A]`
 * immutable + `rol_app REVOKE DELETE`): see `cerrarTurnoChain.ts` for
 * the helper logic; the orchestrator maps each result kind to a
 * banner / navigate call.
 *
 * NO retry loop. NO client-side DELETE (canon §1-§3 forbids physical
 * DELETE on `[A]` tables).
 */
import { useEffect, useRef, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useNavigate } from 'react-router-dom';

import { useDashboardDrawerStore } from '@/store/dashboardDrawerStore';
import type { ResumenCierreTurnoRead } from '../../../lib/api/schemas/resumen-cierre-turno';
import { getResumenCierreTurno } from '../api/resumenCierreTurnoApi';
import type { ArqueoSubmitResult } from '../hooks/useArqueo';
import { logoutAfterClose, useSesionActiva } from '../hooks/useSesionActiva';
import { useResumenCierrePendiente } from '../hooks/useResumenCierrePendiente';
import { useArqueo } from '../hooks/useArqueo';
import { useTipoArqueoPorCodigo } from '../hooks/useTipoArqueoPorCodigo';
import {
  cerrarTurnoSchema,
  type CerrarTurnoInput,
} from '../api/schemas/turnoSchema';
import {
  CerrarTurnoForm,
  type CerrarTurnoErrorState,
} from '../components/CerrarTurnoForm';
import { ResumenCierreTurno } from '../components/ResumenCierreTurno';
import type { SesionRead } from '../api/sesionActivaApi';
import {
  runCerrarTurnoChain,
  type CerrarTurnoBridge,
  type CerrarSesionHelper,
  type ArqueoSubmitFn,
} from './cerrarTurnoChain';

/** Max wait for the (best-effort) post-close detail before showing the summary without it. */
const RESUMEN_TIMEOUT_MS = 10_000;

export function CerrarTurno(): JSX.Element | null {
  const navigate = useNavigate();
  const { sesion, cerrarSesion: cerrarSesionHelper } = useSesionActiva();
  const { submit: submitArqueo } = useArqueo();
  // F11.3: the BE arqueo POST requires `uuid_tipo_arqueo` (UUID), not
  // the legacy codigo string — resolve it via the catalog SWR hook
  // (mirrors `ArqueoParcial.tsx`, HU-F10.1).
  const { uuid: uuidTipoArqueo } = useTipoArqueoPorCodigo('cierre_turno');
  const [errorState, setErrorState] = useState<CerrarTurnoErrorState>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  // Sticky: once the backend tells us a justificación is required
  // (real server-side diferencia, "conteo ciego" hides it from the
  // pre-flight race — see cerrarTurnoChain.ts), force the motivo
  // (Observaciones) to be required for every subsequent attempt in this
  // session, regardless of what the pre-flight says.
  const [forceRequireMotivo, setForceRequireMotivo] = useState(false);

  // PT-5: data for the read-only post-close summary. While set, the
  // summary replaces the form; `sesion` from `useSesionActiva` may already
  // be null (the closed turn answers 404 on /sesion/me), so the closed
  // sesion is kept here.
  const [cierre, setCierre] = useState<{
    sesion: SesionRead;
    arqueo: ArqueoSubmitResult;
    observaciones: string | undefined;
    resumen: ResumenCierreTurnoRead | null;
  } | null>(null);
  const setResumenPendiente = useResumenCierrePendiente((s) => s.setPendiente);
  // Deferred logout bookkeeping: `true` between "PUT cerrar succeeded" and
  // "operator dismissed the summary".
  const logoutPendienteRef = useRef(false);

  const runDeferredLogout = (): boolean => {
    if (!logoutPendienteRef.current) return false;
    logoutPendienteRef.current = false;
    setResumenPendiente(false);
    logoutAfterClose();
    return true;
  };

  // Safety net: if the sheet is dismissed (Esc, overlay) while the summary
  // is still pending, the turn is already closed server-side — log out
  // instead of leaving an authenticated operator without a turno.
  const runDeferredLogoutRef = useRef(runDeferredLogout);
  runDeferredLogoutRef.current = runDeferredLogout;
  useEffect(() => {
    // Also covers a renderer reload / window close with the summary open
    // (an unmount effect does not run then).
    const onPageHide = (): void => {
      runDeferredLogoutRef.current();
    };
    window.addEventListener('pagehide', onPageHide);
    return () => {
      window.removeEventListener('pagehide', onPageHide);
      runDeferredLogoutRef.current();
    };
  }, []);

  const form = useForm<CerrarTurnoInput>({
    resolver: zodResolver(cerrarTurnoSchema),
    mode: 'onBlur',
    defaultValues: {
      valor_efectivo_reportado: 0,
      observaciones_cierre: '',
    },
  });

  const onCancel = (): void => {
    navigate('/');
  };

  const onFinalizar = (): void => {
    runDeferredLogout();
    // Drawer state outlives the route change: close it so the next login
    // does not flash a stale "Cerrar turno" drawer.
    useDashboardDrawerStore.getState().close();
    navigate('/login?closed=true', { replace: true });
  };

  // NOTE: `<CerrarTurnoForm>` wraps this handler with its own
  // `form.handleSubmit(onSubmit)` internally (DEC-F3.3-06 verbatim —
  // same pattern as `<AbrirTurnoForm>`'s sibling contract), so `onSubmit`
  // here MUST stay the raw `(data: CerrarTurnoInput) => Promise<void>`
  // handler. Wrapping it AGAIN with `form.handleSubmit(...)` on this side
  // double-wraps it into a native `(e?: BaseSyntheticEvent) => Promise<void>`
  // handler, which both breaks the `CerrarTurnoFormProps.onSubmit` contract
  // and would mean the values are validated/parsed twice.
  const onSubmit = async (
    values: CerrarTurnoInput,
    ctx?: { requiereJustificacion: boolean },
  ): Promise<void> => {
    if (!sesion) return;
    if (!uuidTipoArqueo) {
      // Bugfix (2026-10-01): this used to `return` silently, leaving
      // the operator with a dead button and nothing in the console —
      // the catalog lookup (`useTipoArqueoPorCodigo`) can still be
      // loading, or have failed, when the operator clicks submit.
      setErrorState({ kind: 'catalogo_no_disponible' });
      return;
    }
    setErrorState(null);
    setIsSubmitting(true);

    // Wire the bridge if available (jsdom + vitest may not have it).
    //
    // KNOWN GAP (found while fixing tsc errors post-rediseño,
    // 2026-09-25): `CerrarTurnoBridge.imprimir(kind, payload)`
    // (cerrarTurnoChain.ts) assumes a 2-arg bridge, but the REAL
    // preload bridge (`electron/preload.ts` `buildImprimir()`) only
    // accepts ONE arg (`payload`) — calling it with 2 args silently
    // drops the payload object (JS binds only the declared param), the
    // same latent bug already present for the identical 2-arg
    // `bridge.imprimir(kind, payload)` convention used by
    // `SalidaMensualidad.tsx` / `PagoSheet.tsx`. Fixing the real
    // contract is out of scope here (owned by `cerrarTurnoChain.ts` /
    // `electron/preload.ts` / `bridge.d.ts`); this cast only restores
    // type-checking without changing the pre-existing runtime behavior.
    const bridge: CerrarTurnoBridge | null =
      typeof window !== 'undefined' &&
      typeof window.bridge?.imprimir === 'function'
        ? {
            // Deliberate double-cast, see the KNOWN GAP comment above:
            // preserves pre-existing (broken) runtime behavior without
            // fabricating a fix for the missing arqueo ticket buffer.
            imprimir: window.bridge.imprimir.bind(
              window.bridge,
            ) as unknown as CerrarTurnoBridge['imprimir'],
          }
        : null;

    const result = await runCerrarTurnoChain({
      sesion,
      uuidTipoArqueo,
      submitArqueo: submitArqueo as unknown as ArqueoSubmitFn,
      cerrarSesion: cerrarSesionHelper as unknown as CerrarSesionHelper,
      bridge,
      values,
      requiereJustificacion: ctx?.requiereJustificacion === true,
    });

    if (result.kind === 'cierre_completado') {
      // The sesion is closed. Keep the token (logout is deferred) and
      // flag the dashboard so it does not redirect to "abrir turno".
      logoutPendienteRef.current = true;
      setResumenPendiente(true);
      // Totals per medio de pago + nº de transacciones come from the new
      // read-only endpoint. Best effort: if it fails the summary still shows
      // the arqueo reconciliation, base and hora de cierre.
      let resumen: ResumenCierreTurnoRead | null = null;
      try {
        // Bounded wait: the turno is already closed, so a slow detail call
        // must not keep the operator staring at a spinning "Confirmar".
        resumen = await Promise.race([
          getResumenCierreTurno(sesion.uuid),
          new Promise<never>((_, reject) =>
            setTimeout(() => reject(new Error('resumen-cierre timeout')), RESUMEN_TIMEOUT_MS),
          ),
        ]);
      } catch (err) {
        console.error('[CerrarTurno] resumen-cierre unavailable', err);
      }
      setCierre({
        sesion: result.sesion,
        arqueo: result.arqueo,
        observaciones: result.observaciones,
        resumen,
      });
      setIsSubmitting(false);
      return;
    }

    setIsSubmitting(false);

    switch (result.kind) {
      case 'redirect_login':
        navigate('/login');
        return;
      case 'arqueo_fallido':
        setErrorState({ kind: 'arqueo_fallido' });
        return;
      case 'justificacion_requerida':
        setForceRequireMotivo(true);
        setErrorState({ kind: 'arqueo_fallido' });
        return;
      case 'red_arqueo':
        setErrorState({ kind: 'red_arqueo' });
        return;
      case 'cierre_ya_cerrado':
        setErrorState({
          kind: 'cierre_ya_cerrado',
          uuid_arqueo: result.uuid_arqueo,
        });
        return;
      case 'cierre_fallido':
        setErrorState({
          kind: 'cierre_fallido',
          uuid_arqueo: result.uuid_arqueo,
        });
        return;
    }
  };

  // PT-5: post-close read-only summary (replaces the form; logout deferred).
  if (cierre !== null) {
    return (
      <ResumenCierreTurno
        sesion={cierre.sesion}
        arqueo={cierre.arqueo}
        observaciones={cierre.observaciones}
        resumen={cierre.resumen}
        onFinalizar={onFinalizar}
      />
    );
  }

  // Sin sesión activa → el Dashboard redirect (T4) lo manejará.
  // Render defensivo: si llegamos aquí sin sesion, retornamos null.
  if (!sesion) return null;

  return (
    <CerrarTurnoForm
      form={form}
      onSubmit={onSubmit}
      isSubmitting={isSubmitting}
      error={errorState}
      sesion={sesion}
      onCancel={onCancel}
      requiredMode="cierre_turno"
      forceRequireMotivo={forceRequireMotivo}
    />
  );
}