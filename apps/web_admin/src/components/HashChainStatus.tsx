/**
 * `<HashChainStatus />` — badge verde/rojo para una fila de
 * `log_transaccional` (HU-F15.2 T3, `plan.md:3552`).
 *
 * Recibe `hashAnterior` y `hashActual` como strings hex SHA-256.
 * Se renderiza verde cuando la cadena está presente (ambos
 * definidos), rojo si falta cualquiera de los dos. La verificación
 * criptográfica completa (`sha256(prev_hash || payload) ==
 * hash_actual`) la hace el `job_sync_cloud.hash_chain_verifier_loop`
 * server-side; acá solo reflejamos el estado reportado por el row.
 *
 * El badge es deliberadamente minimal — un círculo de color, un
 * título accesible que explica el estado, y el par de hashes
 * abreviados (8 hex chars cada uno, mismo patrón que `LogTable`).
 *
 * Reutilizado por:
 *   - EmpresaBitacoraTab (HU-F15.2, este PR).
 *   - Fase 20 (claim/reclamos) que reutilizará el badge.
 */
import { CheckCircle2, XCircle } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

export interface HashChainStatusProps {
  hashAnterior: string | null | undefined;
  hashActual: string | null | undefined;
  /** Cuando `true`, no muestra los hashes abreviados — solo el ícono. */
  compact?: boolean;
  className?: string;
}

function abbreviate(hash: string | null | undefined): string {
  if (hash === null || hash === undefined || hash.length === 0) return '—';
  return `${hash.slice(0, 8)}…`;
}

export function HashChainStatus({
  hashAnterior,
  hashActual,
  compact = false,
  className,
}: HashChainStatusProps): JSX.Element {
  const intact = Boolean(hashAnterior) && Boolean(hashActual);
  const Icon = intact ? CheckCircle2 : XCircle;
  const label = intact
    ? 'Cadena íntegra'
    : 'Cadena rota — falta hash_anterior o hash_actual';
  const testId = intact ? 'hash-chain-intact' : 'hash-chain-broken';

  return (
    <Badge
      variant={intact ? 'secondary' : 'destructive'}
      className={cn(
        'inline-flex items-center gap-1 font-mono text-xs',
        className,
      )}
      data-testid={testId}
      title={`${label} — ${hashAnterior ?? '?'} → ${hashActual ?? '?'}`}
    >
      <Icon className="size-3.5" aria-hidden="true" />
      {compact ? null : (
        <span className="inline-flex items-center gap-1">
          <span className="text-muted-foreground">{abbreviate(hashAnterior)}</span>
          <span aria-hidden="true">→</span>
          <span>{abbreviate(hashActual)}</span>
        </span>
      )}
      <span className="sr-only">{label}</span>
    </Badge>
  );
}
