/**
 * ``AlertaLink`` -- presentational link to the audit log for the
 * alerta row generated when an arqueo had ``diferencia != 0``
 * (DEC-ARQUEO-05, KD-ARQUEO-05).
 *
 * The arqueo row carries ``uuid_sesion`` (nullable) and the handler
 * inserts an ``Alerta`` row with ``uuid_arqueo`` FK + ``accion='descuadre_critico'``
 * whenever the descuadre threshold is exceeded. This component receives
 * ``uuidAlerta`` and renders a single anchor that opens the Audit
 * Dashboard filtered to that alert's row.
 *
 * The actual filter (``?uuid_alerta=...``) isn't wired yet on the BE
 * AuditDashboard -- F18.2 ships the visual integration, F18.4 (PDF
 * export) and F20.4 (bitácora global) extend the link to land at the
 * correct row. Until then, the link is a static anchor that drops
 * the operator on the unauthenticated cross-session view; ``uuidAlerta``
 * is included as the path part for forward-compat.
 */
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

export interface AlertaLinkProps {
  uuidAlerta: string | null;
}

export function AlertaLink({ uuidAlerta }: AlertaLinkProps): JSX.Element | null {
  const { t } = useTranslation();

  if (!uuidAlerta) return null;

  return (
    <Link
      to={`/audit?uuid_alerta=${encodeURIComponent(uuidAlerta)}`}
      data-testid="arqueo-alerta-link"
      className="inline-flex items-center gap-1 rounded-md border border-destructive/50 bg-destructive/10 px-3 py-1 text-xs text-destructive hover:bg-destructive/20"
    >
      {t('arqueos.detail.viewAlerta', 'Ver alerta generada')}
    </Link>
  );
}