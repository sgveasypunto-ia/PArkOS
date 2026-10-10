/**
 * `<PageHeader />` — header estándar de página para todas las rutas
 * autenticadas de `web_admin` (HU-homologar-page-header).
 *
 * Bakea el H1 canónico (`text-2xl font-bold tracking-tight`), el
 * subtítulo (`text-sm text-muted-foreground`) y un slot `actions` a la
 * derecha. Es la ÚNICA fuente de verdad para la fila de título de
 * página: antes había 3 flavors distintos en /catalogos, /empresa,
 * /arqueos, /alertas, /dian, /auditoria/log, /usuarios y
 * /seleccionar-sucursal — la navegación entre rutas se sentía
 * inconsistente.
 *
 * Layout:
 *   - Mobile-first: el cluster `actions` cae debajo del título+subtítulo
 *     (flex-col en mobile → sm:flex-row sm:items-end sm:justify-between).
 *   - Subtítulo es opt-in: si la página no tiene copy secundario, no se
 *     renderiza el `<p>` y el H1 mantiene su jerarquía sin hueco.
 *
 * El `data-testid` en el `<header>` es estable para los tests existentes
 * que pineaban el `<h1>` o el header por composición (p.ej.
 * `UsuariosList.test.tsx` busca el título por texto, no por selector de
 * clase, así que no rompe).
 */
import type { ReactNode } from 'react';

import { cn } from '@/lib/utils';

export interface PageHeaderProps {
  title: string;
  /** Subtítulo o bloque descriptivo secundario (opcional).
   *  Default: string. Acepta ReactNode para vistas que necesitan un
   *  caption/link/aviso dentro del bloque izquierdo del header
   *  (ej. Pairing, donde el browser-scope-caption vive acá). */
  subtitle?: string | ReactNode;
  /** Cluster derecho de botones / acciones (opcional). */
  actions?: ReactNode;
  /** Hook para extender el wrapper — usar con moderación. */
  className?: string;
}

export function PageHeader({
  title,
  subtitle,
  actions,
  className,
}: PageHeaderProps): JSX.Element {
  return (
    <header
      data-testid="page-header"
      className={cn(
        'flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between sm:gap-4',
        className,
      )}
    >
      <div className="space-y-1.5">
        <h1
          className="text-2xl font-bold tracking-tight"
          data-testid="page-header-title"
        >
          {title}
        </h1>
        {subtitle !== undefined && subtitle !== '' && (
          <div
            className="text-sm text-muted-foreground space-y-1.5"
            data-testid="page-header-subtitle"
          >
            {subtitle}
          </div>
        )}
      </div>
      {actions !== undefined && (
        <div
          className="flex shrink-0 flex-wrap items-center gap-2"
          data-testid="page-header-actions"
        >
          {actions}
        </div>
      )}
    </header>
  );
}
