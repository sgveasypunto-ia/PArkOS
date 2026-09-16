/**
 * `<CerrarTurno />` — container (F3.3 — T3, DEC-F3.3-03 + DEC-F3.3-06 + DEC-F3.3-07).
 *
 * Orquesta RHF + Zod resolver + `useSesionActiva()` (sesion.uuid) +
 * `sesionActivaApi.cerrarSesion(uuid, payload)` con logout implícito post-200
 * (DEC-F3.3-03) + dispatch `parkos:auth:cleared` (forward hook AuthGuard F3.x+)
 * + `navigate('/login?closed=true')`.
 *
 * 404 `sesion_not_found` → `<CerrarTurnoForm error.sesion_already_closed>` +
 * `navigate('/login')` (sin `?closed=true` — no fue cierre exitoso).
 *
 * DEC-F3.3-06 placeholder: form simple `valor_final_*` + `observaciones_cierre`.
 * NO consume `POST /caja/arqueo` (Fase 10 entrega flujo completo con tolerancia +
 * justificación + alerta `descuadre_critico`).
 *
 * WCAG 2.1 AA: shadcn Form primitives (form.tsx) proveen `aria-invalid` +
 * `aria-describedby` + `<FormMessage role="alert">` automático.
 */
import { useCallback, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useNavigate } from 'react-router-dom';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import { useSesionActiva } from '../hooks/useSesionActiva';
import {
  cerrarSesion,
  SesionAlreadyClosedError,
  type SesionRead,
} from '../api/sesionActivaApi';
import {
  cerrarTurnoSchema,
  type CerrarTurnoInput,
} from '../api/schemas/turnoSchema';
import {
  CerrarTurnoForm,
  type CerrarTurnoErrorState,
} from '../components/CerrarTurnoForm';

export function CerrarTurno(): JSX.Element {
  const navigate = useNavigate();
  const { sesion } = useSesionActiva();
  const [errorState, setErrorState] = useState<CerrarTurnoErrorState>(null);

  const form = useForm<CerrarTurnoInput>({
    resolver: zodResolver(cerrarTurnoSchema),
    mode: 'onBlur',
    defaultValues: {
      valor_final_efectivo: 0,
      valor_final_datafono: 0,
      observaciones_cierre: '',
    },
  });

  // DEC-F3.3-03: logout implícito post-200 (atómico).
  // El orden importa — clear() primero para que el redirect NO encuentre
  // useSesionActiva activo (key null sin token en T1 SWR config).
  const handleSuccess = useCallback((): void => {
    useAuthStore.getState().clear();
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new Event('parkos:auth:cleared'));
    }
    navigate('/login?closed=true', { replace: true });
  }, [navigate]);

  const onCancel = (): void => {
    navigate('/');
  };

  const onSubmit = form.handleSubmit(async (values) => {
    if (!sesion) return;
    setErrorState(null);
    try {
      const sesionCerrada: SesionRead = await cerrarSesion(sesion.uuid, {
        valor_final_efectivo: values.valor_final_efectivo,
        valor_final_datafono: values.valor_final_datafono,
        ...(values.observaciones_cierre !== undefined && values.observaciones_cierre !== ''
          ? { observaciones_cierre: values.observaciones_cierre }
          : {}),
      });
      void sesionCerrada;
      handleSuccess();
    } catch (err) {
      if (err instanceof SesionAlreadyClosedError) {
        // DEC-F3.3-07: 404 sesion_not_found → redirect login SIN ?closed=true.
        navigate('/login');
      } else if (err instanceof ParkosHttpError && err.status === 401) {
        // 401 mid-flow (refresh failed) → treat like success para consistency.
        handleSuccess();
      } else {
        setErrorState({ kind: 'network' });
      }
    }
  });

  // Sin sesión activa → el Dashboard redirect (T4) lo manejará.
  // Render defensivo: si llegamos aquí sin sesion, retornamos null.
  if (!sesion) return null;

  return (
    <CerrarTurnoForm
      form={form}
      onSubmit={onSubmit}
      isSubmitting={form.formState.isSubmitting}
      error={errorState}
      sesion={sesion}
      onCancel={onCancel}
    />
  );
}