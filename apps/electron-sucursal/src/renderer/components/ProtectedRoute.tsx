import type { ReactNode } from 'react';
import { useEffect } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '@parkos/ui-kit/hooks';

/**
 * `<ProtectedRoute>` — DEC-F3.x auth guard pattern.
 *
 * Cualquier pantalla del feature caja que requiere sesión iniciada
 * (Dashboard, AbrirTurno, CerrarTurno) se envuelve con este guard.
 *
 * Comportamiento:
 *   - isLoading=true          → render Skeleton neutral (no flash de "sesión
 *                                no iniciada" durante refetch 50min)
 *   - isAuthenticated=false   → <Navigate to="/login" replace state.from={location}>
 *                                (redirect transaccional, F3.1 DEC-F3.1-07)
 *   - isAuthenticated=true    → renderiza children
 *
 * Regla del plan (línea 363 §0.2 + DEC-SUC-01): cada sucursal tiene UNA
 * sola sede por instalación/token (branch-pinned). NO existe selector de
 * sucursal en la UI — `uuid_sucursal` viene del JWT.
 */
export function ProtectedRoute({ children }: { children: ReactNode }): JSX.Element {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  useEffect(() => {
    // F3.3 — forward hook: emitir evento para analytics si redirect fue por auth.
    if (!isLoading && !isAuthenticated) {
      if (typeof window !== 'undefined') {
        window.dispatchEvent(
          new CustomEvent('parkos:auth:redirect', {
            detail: { from: location.pathname + location.search },
          }),
        );
      }
    }
  }, [isLoading, isAuthenticated, location]);

  if (isLoading) {
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

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return <>{children}</>;
}
