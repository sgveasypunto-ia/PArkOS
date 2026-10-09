/**
 * `<Pairing />` — HU-F19.3 "Pairing de sucursales" admin screen.
 *
 * Lists every sucursal with a derived pairing-status badge and two row
 * actions, both ALWAYS enabled: "Generar token", and "Revocar" (opens
 * `<RevocarPairingModal />`, whose own two independent sections each
 * gate their own actionability — Section A disables itself when there
 * is no locally-known token to revoke; Section B, the advanced
 * sync-credential revoke, needs no local record at all. The row button
 * itself must stay unconditionally enabled or Section B becomes
 * unreachable for exactly the common case it exists for: a sucursal
 * with no locally-known pairing token, e.g. a different browser/
 * session, or after this one revoked/expired — bugfix, QA batch
 * pairing).
 *
 * BR4 (real-world gap, no clean backend answer — documented workaround,
 * do not re-derive a different one): `GET /api/v1/sucursales` hardcodes
 * `last_pairing_at` to `null` server-side, and there is no "list
 * pairing tokens by uuid_sucursal" endpoint. A sucursal's pairing
 * status therefore CANNOT be derived from any backend call alone. This
 * page only "knows" a sucursal's status for tokens issued from this
 * screen in the CURRENT browser (`lib/pairingLocalState.ts`): for each
 * sucursal that has a locally-known `pairingTokenUuid`, it calls
 * `GET /admin/pairing-tokens/{uuid}` (one call per sucursal WITH a
 * local record only) to derive the live badge. This is a known,
 * intentional, cross-browser/cross-session blind spot — the caption
 * below says so explicitly.
 */
import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import useSWR from 'swr';
import { useTranslation } from 'react-i18next';

import { Badge, type BadgeProps } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

import { useSucursalesDirectorio } from '@/features/sucursales/hooks/useSucursalesDirectorio';
import type { Sucursal } from '@/features/sucursales/api/sucursalSchema';

import { GenerarPairingTokenModal } from '../components/GenerarPairingTokenModal';
import { RevocarPairingModal } from '../components/RevocarPairingModal';
import { PairingTokenNotFoundError, getPairingToken } from '../api/pairingApi';
import type { PairingTokenIssueResponse, PairingTokenRead } from '../api/pairingSchema';
import {
  deleteLocalRecord,
  getLastTokenUuid,
  setLastTokenUuid,
} from '../lib/pairingLocalState';

type PairingStatus = 'sinInformacion' | 'pendiente' | 'pareada' | 'revocado' | 'expirado';

const STATUS_BADGE: Record<
  PairingStatus,
  { labelKey: string; fallback: string; variant: NonNullable<BadgeProps['variant']> }
> = {
  sinInformacion: {
    labelKey: 'pairing.status.sinInformacion',
    fallback: 'Sin información',
    variant: 'outline',
  },
  pendiente: {
    labelKey: 'pairing.status.pendiente',
    fallback: 'Pendiente',
    variant: 'secondary',
  },
  pareada: { labelKey: 'pairing.status.pareada', fallback: 'Pareada', variant: 'success' },
  revocado: {
    labelKey: 'pairing.status.revocado',
    fallback: 'Revocado',
    variant: 'destructive',
  },
  expirado: { labelKey: 'pairing.status.expirado', fallback: 'Expirado', variant: 'warning' },
};

function derivePairingStatus(params: {
  hasLocalRecord: boolean;
  notFound: boolean;
  read: PairingTokenRead | undefined;
}): PairingStatus {
  const { hasLocalRecord, notFound, read } = params;
  if (!hasLocalRecord || notFound) return 'sinInformacion';
  if (read === undefined) return 'sinInformacion';
  if (read.revoked_at !== null) return 'revocado';
  if (!read.used && new Date(read.expires_at).getTime() <= Date.now()) return 'expirado';
  if (read.used) return 'pareada';
  return 'pendiente';
}

interface PairingRowProps {
  sucursal: Sucursal;
  /** Bumped by the parent after an issue/revoke so this row re-reads localStorage + revalidates. */
  localVersion: number;
  onGenerar: (sucursal: Sucursal) => void;
  onRevocar: (sucursal: Sucursal, pairingTokenUuid: string | null) => void;
}

function PairingRow({ sucursal, localVersion, onGenerar, onRevocar }: PairingRowProps): JSX.Element {
  const { t } = useTranslation();
  const pairingTokenUuid = getLastTokenUuid(sucursal.uuid);

  const { data, error } = useSWR<PairingTokenRead>(
    pairingTokenUuid ? `pairing-token-status:${pairingTokenUuid}:${localVersion}` : null,
    () => getPairingToken(pairingTokenUuid as string),
    { revalidateOnFocus: false },
  );

  // 2026-10-08 UX fix: when the cached UUID no longer exists on the
  // server (DB was reseeded, token was issued in a different browser,
  // etc.) the GET returns 404 — the row genuinely doesn't exist, so
  // the server's response is correct. The localStorage record is
  // now stale; evict it once and force this row to re-render so
  // ``getLastTokenUuid`` returns null on the next pass (SWR key
  // becomes null → no further GETs, badge collapses to
  // ``sinInformacion``). Without this, every page load keeps
  // firing the 404 — the network panel fills up and the user
  // can't tell which rows are "real" 404s vs. resolved ones.
  const [evicted, setEvicted] = useState(false);
  const notFound = error instanceof PairingTokenNotFoundError;
  useEffect(() => {
    if (notFound && !evicted) {
      deleteLocalRecord(sucursal.uuid);
      setEvicted(true);
    }
  }, [notFound, evicted, sucursal.uuid]);

  const status = derivePairingStatus({
    hasLocalRecord: pairingTokenUuid !== null,
    notFound,
    read: data,
  });
  const badge = STATUS_BADGE[status];

  return (
    <TableRow data-testid={`pairing-row-${sucursal.uuid}`}>
      <TableCell className="font-medium">{sucursal.nombre ?? sucursal.uuid}</TableCell>
      <TableCell className="font-mono text-xs">{sucursal.prefijo_nombre ?? '—'}</TableCell>
      <TableCell>{sucursal.ciudad ?? '—'}</TableCell>
      <TableCell>
        <Badge variant={badge.variant} data-testid={`pairing-status-${sucursal.uuid}`}>
          {t(badge.labelKey, badge.fallback)}
        </Badge>
      </TableCell>
      <TableCell className="text-right">
        <div className="flex justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => onGenerar(sucursal)}
            data-testid={`pairing-generar-${sucursal.uuid}`}
          >
            {t('pairing.action.generar', 'Generar token')}
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => onRevocar(sucursal, pairingTokenUuid)}
            data-testid={`pairing-revocar-${sucursal.uuid}`}
          >
            {t('pairing.action.revocar', 'Revocar')}
          </Button>
        </div>
      </TableCell>
    </TableRow>
  );
}

export default function Pairing(): JSX.Element {
  const { t } = useTranslation();
  const [searchParams] = useSearchParams();
  const { sucursales, isLoading, error } = useSucursalesDirectorio();

  const [localVersion, setLocalVersion] = useState(0);
  const [generarFor, setGenerarFor] = useState<Sucursal | null>(null);
  const [revocarFor, setRevocarFor] = useState<{
    sucursal: Sucursal;
    pairingTokenUuid: string | null;
  } | null>(null);

  const autoOpenUuid = searchParams.get('sucursal');
  const autoOpenedRef = useRef(false);

  // Nice-to-have: `?sucursal=<uuid>` auto-opens the issue modal for
  // that row once the branch list has loaded.
  useEffect(() => {
    if (autoOpenedRef.current || autoOpenUuid === null || sucursales.length === 0) return;
    const match = sucursales.find((s) => s.uuid === autoOpenUuid);
    if (match) {
      setGenerarFor(match);
      autoOpenedRef.current = true;
    }
  }, [autoOpenUuid, sucursales]);

  function handleIssued(sucursal: Sucursal, resp: PairingTokenIssueResponse): void {
    setLastTokenUuid(sucursal.uuid, resp.pairing_token_uuid);
    setLocalVersion((v) => v + 1);
  }

  return (
    <main className="space-y-4 p-4 md:p-6" data-testid="pairing-page">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">
          {t('pairing.title', 'Pairing de sucursales')}
        </h1>
        <p className="text-sm text-muted-foreground">
          {t(
            'pairing.subtitle',
            'Generá y revocá tokens de pairing para conectar el agente de sincronización de cada sucursal.',
          )}
        </p>
        <p className="text-xs text-muted-foreground" data-testid="pairing-browser-scope-caption">
          {t(
            'pairing.browserScopeCaption',
            'Esta vista solo refleja los tokens emitidos desde este navegador. Un token emitido desde otra sesión no aparece acá.',
          )}
        </p>
      </header>

      {error !== undefined && (
        <p
          role="alert"
          aria-live="assertive"
          data-testid="pairing-list-error"
          className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {t('pairing.loadError', 'No se pudieron cargar las sucursales.')}
        </p>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t('pairing.listTitle', 'Sucursales')}</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading && sucursales.length === 0 ? (
            <p role="status" aria-live="polite" className="text-sm text-muted-foreground">
              {t('pairing.loading', 'Cargando sucursales...')}
            </p>
          ) : sucursales.length === 0 ? (
            <p
              role="status"
              aria-live="polite"
              data-testid="pairing-empty"
              className="text-sm text-muted-foreground"
            >
              {t('pairing.empty', 'Aún no hay sucursales configuradas.')}
            </p>
          ) : (
            <Table data-testid="pairing-table">
              <TableCaption className="sr-only">
                {t('pairing.listTitle', 'Sucursales')}
              </TableCaption>
              <TableHeader>
                <TableRow>
                  <TableHead scope="col">{t('pairing.col.nombre', 'Nombre')}</TableHead>
                  <TableHead scope="col">{t('pairing.col.prefijo', 'Prefijo')}</TableHead>
                  <TableHead scope="col">{t('pairing.col.ciudad', 'Ciudad')}</TableHead>
                  <TableHead scope="col">{t('pairing.col.estado', 'Estado')}</TableHead>
                  <TableHead scope="col" className="text-right">
                    {t('pairing.col.acciones', 'Acciones')}
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sucursales.map((s) => (
                  <PairingRow
                    key={s.uuid}
                    sucursal={s}
                    localVersion={localVersion}
                    onGenerar={setGenerarFor}
                    onRevocar={(sucursal, pairingTokenUuid) =>
                      setRevocarFor({ sucursal, pairingTokenUuid })
                    }
                  />
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {generarFor !== null && (
        <GenerarPairingTokenModal
          key={generarFor.uuid}
          sucursalUuid={generarFor.uuid}
          sucursalNombre={generarFor.nombre}
          open
          onClose={() => setGenerarFor(null)}
          onIssued={(resp) => handleIssued(generarFor, resp)}
        />
      )}

      {revocarFor !== null && (
        <RevocarPairingModal
          key={revocarFor.sucursal.uuid}
          sucursalUuid={revocarFor.sucursal.uuid}
          sucursalNombre={revocarFor.sucursal.nombre}
          pairingTokenUuid={revocarFor.pairingTokenUuid}
          open
          onClose={() => setRevocarFor(null)}
          onRevoked={() => setLocalVersion((v) => v + 1)}
        />
      )}
    </main>
  );
}
