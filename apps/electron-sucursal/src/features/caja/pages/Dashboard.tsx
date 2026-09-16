/**
 * `<Dashboard />` — container (F3.3 — T4, DEC-F3.3-05 verbatim).
 *
 * Página `/` que consume `useSesionActiva()` (T1 hook) y decide redirect
 * atómicamente via `useEffect([sesion, isLoading, error])`:
 *
 *   (a) `sesion === null && !isLoading && !error`
 *       → `navigate('/caja/abrir-turno', { replace: true })`
 *       (replace previene back-button infinite loop — operador kiosko no
 *       vuelve al dashboard presionando back).
 *
 *   (b) `sesion !== null`
 *       → renderiza `<TurnoActivoPanel sesion onCerrarClick={() => navigate('/caja/cerrar-turno')} />`
 *       (REQ-OPS-121 organism).
 *
 *   (c) `isLoading === true`
 *       → render `<Skeleton>` neutral (no flash de "sesión no iniciada"
 *       durante refetch 50min).
 *
 *   (d) `error && status !== 404`
 *       → render error state con retry button.
 *
 * DEC-F3.3-05 single source of truth: Dashboard consume `useSesionActiva`
 * y NO verifica autenticación directamente — futuro `<AuthGuard>` (F3.x+)
 * interceptará `parkos:auth:cleared` y navegará a `/login?next=...`.
 */
import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import { useSesionActiva } from '../hooks/useSesionActiva';
import { TurnoActivoPanel } from '../components/TurnoActivoPanel';
import { Skeleton } from '@/renderer/components/ui/skeleton';
import { Button } from '@/renderer/components/ui/button';

export function Dashboard(): JSX.Element {
  const { sesion, isLoading, error, refresh } = useSesionActiva();
  const navigate = useNavigate();
  const { t } = useTranslation(['caja', 'common']);

  // DEC-F3.3-05: redirect atómico cuando no hay sesión activa + NO loading + NO error.
  // Deps exhaustivas para evitar loop infinito.
  useEffect(() => {
    if (!sesion && !isLoading && !error) {
      navigate('/caja/abrir-turno', { replace: true });
    }
  }, [sesion, isLoading, error, navigate]);

  // (c) Loading state → Skeleton neutral.
  if (isLoading) {
    return <Skeleton className="h-32 w-full" data-testid="dashboard-skeleton" />;
  }

  // (d) Error state distinto a 404 → error + retry.
  if (error && (error instanceof ParkosHttpError ? error.status !== 404 : true)) {
    return (
      <div data-testid="dashboard-error">
        <p role="alert">{t('common:error')}</p>
        <Button onClick={() => void refresh()} data-testid="dashboard-retry">
          {t('common:retry')}
        </Button>
      </div>
    );
  }

  // (b) Sesión activa → TurnoActivoPanel.
  if (sesion) {
    return (
      <TurnoActivoPanel
        sesion={sesion}
        onCerrarClick={() => navigate('/caja/cerrar-turno')}
      />
    );
  }

  // (a) sin sesión + no loading + no error → el redirect se dispara en el effect.
  // Render defensivo: no flash de "sesión no iniciada" antes del redirect.
  return null;
}