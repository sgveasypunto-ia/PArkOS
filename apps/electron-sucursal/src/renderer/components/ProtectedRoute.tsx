import type { ReactNode } from 'react';
import { useEffect } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '@parkos/ui-kit/hooks';

import { useSesionActiva } from '../../features/caja/hooks/useSesionActiva';

/**
 * `<ProtectedRoute>` — auth + sesión guard (REQ-OPS-136 canon + F3.x family).
 *
 * Cualquier pantalla del feature caja se envuelve con este guard. La cadena
 * de guards es en este orden:
 *
 *   1. **Auth** — `useAuth()` decide si hay token Bearer.
 *      Si NO → redirect `/login` (F3.1 DEC-F3.1-07, redirect transaccional).
 *
 *   2. **Sesión** — `useSesionActiva()` (F3.3 T1) consulta `GET /caja-sesion/sesion/me`.
 *      Si NO hay sesión abierta Y la ruta NO es `/caja/abrir-turno`
 *      → redirect `/caja/abrir-turno` (REQ-OPS-136 canonical routing).
 *      Si HAY sesión Y la ruta ES `/caja/abrir-turno` (operador intentando
 *      abrir un turno cuando ya tiene uno abierto)
 *      → redirect `/` (Dashboard) — consistente con la regla REQ-OPS-136.
 *
 *   3. **Render** — si pasó los 2 guards, renderiza children.
 *
 * Loading state: skeleton neutral mientras auth O sesion están cargando
 * (no flash de "sesión no iniciada" durante refetch 50min de F3.2).
 *
 * Defense in depth: `Dashboard.tsx` también chequea `sesion === null`
 * (REQ-OPS-123) — cuando ProtectedRoute ya redirigió, Dashboard nunca
 * se renderiza con `sesion === null`, así que el useEffect interno
 * es un no-op. Lo dejamos como belt-and-suspenders.
 *
 * Regla del plan (línea 363 §0.2 + DEC-SUC-01): cada sucursal tiene UNA
 * sola sede por instalación/token (branch-pinned). NO existe selector de
 * sucursal en la UI — `uuid_sucursal` viene del JWT.
 */
const SESION_PATH = '/caja/abrir-turno';

export function ProtectedRoute({ children }: { children: ReactNode }): JSX.Element {
  const { isAuthenticated, isLoading: isAuthLoading } = useAuth();
  const { sesion, isLoading: isSesionLoading } = useSesionActiva();
  const location = useLocation();

  useEffect(() => {
    // F3.3 — forward hook: emitir evento para analytics si redirect fue por auth.
    if (!isAuthLoading && !isAuthenticated) {
      if (typeof window !== 'undefined') {
        window.dispatchEvent(
          new CustomEvent('parkos:auth:redirect', {
            detail: { from: location.pathname + location.search },
          }),
        );
      }
    }
  }, [isAuthLoading, isAuthenticated, location]);

  // Loading skeleton: cubre AMBOS fetches (auth bootstrap + sesion SWR).
  if (isAuthLoading || isSesionLoading) {
    return (
      <div
        role="status"
        aria-live="polite"
        className="flex min-h-[50vh] items-center justify-center"
      >
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-muted border-t-primary" />
      </div>
    );
  }

  // Auth gate.
  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  // Sesión gate (REQ-OPS-136).
  // Sesión null + ruta NO es abrir-turno → redirigir a abrir-turno.
  if (sesion === null && location.pathname !== SESION_PATH) {
    return <Navigate to={SESION_PATH} replace />;
  }
  // Sesión activa + ruta ES abrir-turno (operador con turno intentando
  // abrir otro) → redirigir al Dashboard.
  if (sesion !== null && location.pathname === SESION_PATH) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}
