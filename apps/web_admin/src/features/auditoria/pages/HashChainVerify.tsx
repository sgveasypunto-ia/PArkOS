/**
 * `<HashChainVerify />` -- HU-F20.4 on-demand SHA-256 hash-chain
 * verification sweep. "Verificar" is a manually-triggered action (NOT
 * auto-fetched on mount/filter-change, per plan.md's "botón Verificar") --
 * see `hooks/useVerifyChain.ts`'s own docblock for why this is a plain
 * trigger function instead of an auto-revalidating SWR key.
 *
 * CSV export reuses `lib/export/csv.ts::exportToCsv` verbatim (same
 * call shape as `features/reporteria/pages/Reporteria.tsx`) -- the
 * CSV/formula-injection sanitization (`sanitizeCsvCell`) is already
 * applied internally by `buildCsv`, so this page does not call it
 * directly and does not hand-roll a serializer.
 */
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { exportToCsv, type CsvColumn } from '@/lib/export/csv';

import { useSucursalesDirectorio } from '@/features/sucursales/hooks/useSucursalesDirectorio';

import { useVerifyChain } from '../hooks/useVerifyChain';
import {
  VERIFY_CHAIN_TABLAS,
  type ChainAnomalyItem,
  type VerifyChainTabla,
} from '../api/auditoriaSchema';

function short(value: string | null): string {
  if (!value) return '—';
  return value.length > 10 ? `${value.slice(0, 10)}…` : value;
}

const ANOMALY_COLUMNS: CsvColumn<ChainAnomalyItem>[] = [
  { header: 'Tabla', accessor: (r) => r.tabla },
  { header: 'Sucursal', accessor: (r) => r.uuid_sucursal ?? '' },
  { header: 'UUID', accessor: (r) => r.uuid },
  { header: 'Hash esperado', accessor: (r) => r.expected },
  { header: 'Hash actual', accessor: (r) => r.actual ?? '' },
  { header: 'Secuencia', accessor: (r) => r.seq ?? '' },
  { header: 'Motivo', accessor: (r) => r.reason },
];

export default function HashChainVerify(): JSX.Element {
  const { t } = useTranslation();
  const { sucursales } = useSucursalesDirectorio();
  const { result, isLoading, error, verify } = useVerifyChain();

  const [tabla, setTabla] = useState<VerifyChainTabla>('log_transaccional');
  const [uuidSucursal, setUuidSucursal] = useState<string>('');

  const sucursalOptions = useMemo(
    () => sucursales.map((s) => ({ uuid: s.uuid, nombre: s.nombre })),
    [sucursales],
  );

  function handleVerificar(): void {
    void verify({ tabla, uuid_sucursal: uuidSucursal || undefined });
  }

  function handleExportCsv(): void {
    if (!result) return;
    exportToCsv(`verify-chain-${tabla}.csv`, ANOMALY_COLUMNS, result.anomalias);
  }

  return (
    <main className="space-y-4 p-4 md:p-6" data-testid="hash-chain-verify-page">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">
          {t('auditoria.verifyChain.title', 'Verificación de cadena')}
        </h1>
        <p className="text-muted-foreground text-sm">
          {t(
            'auditoria.verifyChain.subtitle',
            'Barrido de integridad SHA-256 a demanda sobre una tabla particionada.',
          )}
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">
            {t('auditoria.verifyChain.formTitle', 'Parámetros')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-4">
            <label className="flex flex-col gap-1 text-xs">
              <span className="font-medium text-muted-foreground">
                {t('auditoria.verifyChain.tabla', 'Tabla')}
              </span>
              <select
                data-testid="hash-chain-verify-tabla"
                value={tabla}
                onChange={(e) => setTabla(e.target.value as VerifyChainTabla)}
                className="rounded-md border bg-background px-2 py-1 text-sm"
              >
                {VERIFY_CHAIN_TABLAS.map((opt) => (
                  <option key={opt} value={opt}>
                    {opt}
                  </option>
                ))}
              </select>
            </label>

            <label className="flex flex-col gap-1 text-xs">
              <span className="font-medium text-muted-foreground">
                {t('auditoria.verifyChain.sucursal', 'Sucursal')}
              </span>
              <select
                data-testid="hash-chain-verify-sucursal"
                value={uuidSucursal}
                onChange={(e) => setUuidSucursal(e.target.value)}
                className="rounded-md border bg-background px-2 py-1 text-sm"
              >
                <option value="">
                  {t('auditoria.verifyChain.allBranches', 'Todas mis sucursales')}
                </option>
                {sucursalOptions.map((s) => (
                  <option key={s.uuid} value={s.uuid}>
                    {s.nombre ?? s.uuid}
                  </option>
                ))}
              </select>
            </label>

            <div className="flex items-end">
              <Button
                type="button"
                onClick={handleVerificar}
                disabled={isLoading}
                data-testid="hash-chain-verify-button"
              >
                {isLoading
                  ? t('auditoria.verifyChain.verifying', 'Verificando...')
                  : t('auditoria.verifyChain.verify', 'Verificar')}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {error && (
        <div
          role="alert"
          data-testid="hash-chain-verify-error"
          className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {error.message}
        </div>
      )}

      {result && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-3">
            <CardTitle className="text-sm">
              {t('auditoria.verifyChain.resultTitle', 'Resultado')}
            </CardTitle>
            <Badge
              variant={result.ok ? 'success' : 'destructive'}
              data-testid="hash-chain-verify-status"
            >
              {result.ok
                ? t('auditoria.verifyChain.ok', 'Cadena íntegra')
                : t('auditoria.verifyChain.anomalias', '{{count}} anomalías', {
                    count: result.anomalias.length,
                  })}
            </Badge>
          </CardHeader>
          <CardContent className="space-y-3">
            {result.ok ? (
              <p className="text-sm text-muted-foreground" data-testid="hash-chain-verify-ok">
                {t(
                  'auditoria.verifyChain.okDescription',
                  'No se encontraron anomalías en la cadena de hashes.',
                )}
              </p>
            ) : (
              <>
                <div className="flex justify-end">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={handleExportCsv}
                    data-testid="hash-chain-verify-export-csv"
                  >
                    {t('auditoria.verifyChain.exportCsv', 'Exportar CSV')}
                  </Button>
                </div>
                <table
                  data-testid="hash-chain-verify-anomalias-table"
                  className="w-full overflow-x-auto rounded-lg border bg-card text-sm"
                >
                  <thead className="bg-muted/40 text-left">
                    <tr>
                      <th scope="col" className="px-3 py-2 font-medium">
                        {t('auditoria.verifyChain.col.tabla', 'Tabla')}
                      </th>
                      <th scope="col" className="px-3 py-2 font-medium">
                        {t('auditoria.verifyChain.col.sucursal', 'Sucursal')}
                      </th>
                      <th scope="col" className="px-3 py-2 font-medium">
                        {t('auditoria.verifyChain.col.uuid', 'UUID')}
                      </th>
                      <th scope="col" className="px-3 py-2 font-medium">
                        {t('auditoria.verifyChain.col.expected', 'Esperado')}
                      </th>
                      <th scope="col" className="px-3 py-2 font-medium">
                        {t('auditoria.verifyChain.col.actual', 'Actual')}
                      </th>
                      <th scope="col" className="px-3 py-2 font-medium">
                        {t('auditoria.verifyChain.col.seq', 'Seq')}
                      </th>
                      <th scope="col" className="px-3 py-2 font-medium">
                        {t('auditoria.verifyChain.col.reason', 'Motivo')}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.anomalias.map((a, idx) => (
                      <tr
                        key={`${a.uuid}-${idx}`}
                        data-testid={`hash-chain-verify-anomalia-${a.uuid}`}
                        className="border-t hover:bg-muted/20"
                      >
                        <td className="px-3 py-2 font-mono text-xs">{a.tabla}</td>
                        <td className="px-3 py-2 font-mono text-xs">{short(a.uuid_sucursal)}</td>
                        <td className="px-3 py-2 font-mono text-xs">{short(a.uuid)}</td>
                        <td className="px-3 py-2 font-mono text-xs">{short(a.expected)}</td>
                        <td className="px-3 py-2 font-mono text-xs">{short(a.actual)}</td>
                        <td className="px-3 py-2 tabular-nums text-xs">{a.seq ?? '—'}</td>
                        <td className="px-3 py-2 text-xs">{a.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </CardContent>
        </Card>
      )}
    </main>
  );
}
