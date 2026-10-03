/**
 * ``AlertaLink`` -- presentational link to the bitácora for the alerta
 * row generated when an arqueo had ``diferencia != 0`` (DEC-ARQUEO-05,
 * KD-ARQUEO-05).
 *
 * The handler inserts an ``Alerta`` row with ``uuid_arqueo`` FK +
 * ``tipo_alerta='descuadre_critico'`` whenever the descuadre threshold
 * is exceeded; that same transaction appends a ``log_transaccional`` row
 * with ``tabla_afectada='alerta'`` + ``uuid_registro_afectado=<alerta.uuid>``
 * (``repo/workflow.py::append_transition``). This component receives
 * ``uuidAlerta`` and renders a single anchor to the REAL bitácora module
 * (``/auditoria/log``, ``features/auditoria/pages/LogTransaccional.tsx``),
 * pre-filtered to that exact log entry via ``?uuid_alerta=``.
 *
 * QA backlog cleanup (2026-10-02): this previously pointed at the LEGACY
 * `/audit` module (`features/audit/AuditDashboard.tsx`), which is not
 * reachable from any real navigation and reads no query param at all —
 * the link always landed on an unfiltered, unauthenticated dead end.
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
      to={`/auditoria/log?uuid_alerta=${encodeURIComponent(uuidAlerta)}`}
      data-testid="arqueo-alerta-link"
      className="inline-flex items-center gap-1 rounded-md border border-destructive/50 bg-destructive/10 px-3 py-1 text-xs text-destructive hover:bg-destructive/20"
    >
      {t('arqueos.detail.viewAlerta', 'Ver alerta generada')}
    </Link>
  );
}