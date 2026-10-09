/**
 * `<AbrirTurno />` — container. Opens the shift without asking for anything.
 *
 * The base de caja is a branch parameter configured by administration
 * (`configuracion_caja`, synced from the cloud). This screen resolves it, opens
 * the shift on its own and leaves a marker so the dashboard shows a notice with
 * the base and who to ask if in doubt (`<BaseCajaAviso>`). The backend resolves
 * the base again server-side and ignores whatever the client sends.
 *
 * 409 `sesion_already_active` keeps its UX ("ya tenés un turno abierto" + "Ir
 * al turno"); a branch without a configured base cannot open a shift.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSWRConfig } from 'swr';

import { useAuth } from '@parkos/ui-kit/hooks';
import { useAuthStore } from '@parkos/ui-kit/store';

import { abrirSesion, SesionAlreadyActiveError } from '../api/sesionActivaApi';
import { AbrirTurnoAviso, type AbrirTurnoStatus } from '../components/AbrirTurnoAviso';
import { useBaseCajaEfectiva } from '../hooks/useBaseCajaEfectiva';
import { SESION_KEY } from '../hooks/useSesionActiva';
import { marcarBaseAviso } from '../lib/baseCajaAviso';

export function AbrirTurno(): JSX.Element {
  const navigate = useNavigate();
  // Cache-bound mutate: the SWR cache is scoped per operator session.
  const { mutate } = useSWRConfig();
  const { user, sucursal } = useAuth();
  const { base, isLoading: baseLoading, error: baseError } = useBaseCajaEfectiva(sucursal?.uuid);

  const [status, setStatus] = useState<AbrirTurnoStatus>('cargando');
  // One open attempt per mount/retry: effects run twice in StrictMode and the
  // backend would answer 409 to the second POST.
  const intentoRef = useRef(0);
  const [reintento, setReintento] = useState(0);

  const abrir = useCallback(async (): Promise<void> => {
    if (sucursal?.uuid === undefined || user?.uuid === undefined) return;
    setStatus('abriendo');
    try {
      const opened = await abrirSesion({
        uuid_sucursal: sucursal.uuid,
        uuid_usuario: user.uuid,
        // Informative only: the server resolves the base itself and ignores
        // both values (the datafono never starts a shift with a value).
        valor_inicial_efectivo: base ?? 0,
        valor_inicial_datafono: 0,
      });
      // Adopt the reissued token pair BEFORE leaving: it carries the `sesion`
      // claim every payment needs so `factura_pagos.uuid_sesion` links to this
      // turno for arqueo.
      useAuthStore
        .getState()
        .setTokens(opened.access_token, opened.refresh_token, opened.expires_in);
      // Push the new session into the SWR cache so the dashboard does not
      // bounce the operator back here (revalidate: false — we already hold the
      // canonical value).
      // The dashboard shows the base notice (this screen unmounts as soon as
      // the session exists), so leave the marker BEFORE the cache write.
      marcarBaseAviso(opened.uuid);
      void mutate(SESION_KEY, opened, { revalidate: false });
      navigate('/', { replace: true });
    } catch (err) {
      if (err instanceof SesionAlreadyActiveError) {
        void mutate(SESION_KEY);
        setStatus('sesion_ya_abierta');
        return;
      }
      setStatus('error');
    }
  }, [base, mutate, navigate, sucursal?.uuid, user?.uuid]);

  useEffect(() => {
    if (baseLoading) {
      setStatus('cargando');
      return;
    }
    if (baseError !== undefined) {
      setStatus('error');
      return;
    }
    if (base === null) {
      setStatus('sin_base');
      return;
    }
    if (intentoRef.current === reintento + 1) return;
    intentoRef.current = reintento + 1;
    void abrir();
  }, [abrir, base, baseError, baseLoading, reintento]);

  return (
    <div
      className="grid min-h-[calc(100vh-2rem)] w-full place-items-center px-4 py-8"
      data-testid="abrir-turno-page-wrapper"
    >
      <div className="w-full max-w-md">
        <AbrirTurnoAviso
          status={status}
          onReintentar={() => {
            void mutate(`/configuracion-caja/efectiva/${sucursal?.uuid ?? ''}`);
            setReintento((n) => n + 1);
          }}
          onIrAlTurno={() => navigate('/')}
        />
      </div>
    </div>
  );
}
