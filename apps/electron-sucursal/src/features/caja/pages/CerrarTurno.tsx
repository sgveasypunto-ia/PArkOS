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
 * `navigate('/login?closed=true')`) is preserved verbatim per Engram
 * #1899 (Q1 ratified 2026-09-21) — the trifecta is now OWNED by
 * `useSesionActiva().cerrarSesion` (REQ-OPS-160, AD-4), so the
 * orchestrator only has to `navigate` on `ok: true`.
 *
 * 8-case error precedence (AD-3, exhaustive against `prod.arqueo [A]`
 * immutable + `rol_app REVOKE DELETE`): see `cerrarTurnoChain.ts` for
 * the helper logic; the orchestrator maps each result kind to a
 * banner / navigate call.
 *
 * NO retry loop. NO client-side DELETE (canon §1-§3 forbids physical
 * DELETE on `[A]` tables).
 */
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useNavigate } from 'react-router-dom';

import { useSesionActiva } from '../hooks/useSesionActiva';
import { useArqueo } from '../hooks/useArqueo';
import {
  cerrarTurnoSchema,
  type CerrarTurnoInput,
} from '../api/schemas/turnoSchema';
import {
  CerrarTurnoForm,
  type CerrarTurnoErrorState,
} from '../components/CerrarTurnoForm';
import {
  runCerrarTurnoChain,
  type CerrarTurnoBridge,
  type CerrarSesionHelper,
  type ArqueoSubmitFn,
} from './cerrarTurnoChain';

export function CerrarTurno(): JSX.Element {
  const navigate = useNavigate();
  const { sesion, cerrarSesion: cerrarSesionHelper } = useSesionActiva();
  const { submit: submitArqueo } = useArqueo();
  const [errorState, setErrorState] = useState<CerrarTurnoErrorState>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const form = useForm<CerrarTurnoInput>({
    resolver: zodResolver(cerrarTurnoSchema),
    mode: 'onBlur',
    defaultValues: {
      valor_final_efectivo: 0,
      valor_final_datafono: 0,
      observaciones_cierre: '',
      valor_efectivo_reportado: 0,
      valor_datafono_reportado: 0,
      justificacion: '',
    },
  });

  const onCancel = (): void => {
    navigate('/');
  };

  const onSubmit = form.handleSubmit(async (values) => {
    if (!sesion) return;
    setErrorState(null);
    setIsSubmitting(true);

    // Wire the bridge if available (jsdom + vitest may not have it).
    const bridge: CerrarTurnoBridge | null =
      typeof window !== 'undefined' &&
      typeof window.bridge?.imprimir === 'function'
        ? { imprimir: window.bridge.imprimir.bind(window.bridge) }
        : null;

    const result = await runCerrarTurnoChain({
      sesion,
      submitArqueo: submitArqueo as unknown as ArqueoSubmitFn,
      cerrarSesion: cerrarSesionHelper as unknown as CerrarSesionHelper,
      bridge,
      values,
    });

    setIsSubmitting(false);

    switch (result.kind) {
      case 'success':
      case 'redirect_login_closed':
        navigate('/login?closed=true', { replace: true });
        return;
      case 'redirect_login':
        navigate('/login');
        return;
      case 'arqueo_fallido':
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
  });

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
    />
  );
}