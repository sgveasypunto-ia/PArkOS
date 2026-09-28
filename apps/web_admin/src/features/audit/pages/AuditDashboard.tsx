/**
 * `<AuditDashboard />` -- container for the IT-12 audit-log dashboard
 * (web_admin).
 *
 * Mirrors the container/presentational split used by
 * ``features/sucursales/pages/SucursalesList.tsx`` and
 * ``features/auth/pages/Login.tsx``:
 *   - This file owns data fetching (SWR + cursor merge), the active
 *     branch selector, and the load-more state.
 *   - ``<LogTable />`` renders the rows.
 *
 * Data flow:
 *   1. Reads the active branch from ``useSucursal()`` (the same
 *      context the Dashboard uses). The audit endpoint REQUIRES
 *      ``uuid_sucursal`` -- rendering with no branch selected surfaces
 *      a hint rather than an empty 200.
 *   2. First page loads via SWR with key
 *      ``/admin/audit/log?uuid_sucursal=...&limit=20``.
 *   3. "Load more" appends the next page (cursor pagination) to the
 *      local state, replacing the SWR cache with the merged result so
 *      revalidation re-fetches the whole list.
 *
 * Why a hybrid (SWR + local merge): SWR doesn't natively support
 * cursor merge; we use SWR for the first page (caching + dedupe) and
 * local state for subsequent pages. This is the same pattern
 * ``features/facturacion/...`` uses for list pagination.
 */
import { useCallback, useState } from 'react';
import useSWR from 'swr';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';

import { fetchAuditLog } from '../api/auditApi';
import { LogTable } from '../components/LogTable';
import { useSucursal } from '@/lib/sucursal-context';
import type { AuditLogItem } from '../api/auditSchema';

function buildSWRKey(uuid_sucursal: string, limit: number): string {
  return `/admin/audit/log?uuid_sucursal=${encodeURIComponent(uuid_sucursal)}&limit=${limit}`;
}

export default function AuditDashboard() {
  const { t } = useTranslation();
  const { selected } = useSucursal();
  const [pageItems, setPageItems] = useState<AuditLogItem[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [isLoadingMore, setIsLoadingMore] = useState(false);

  const firstPageSWR = useSWR(
    selected === null ? null : buildSWRKey(selected, 20),
    async (key: string) => {
      const params = new URLSearchParams(key.split('?')[1] ?? '');
      const uuid_sucursal = params.get('uuid_sucursal') ?? '';
      const limit = Number(params.get('limit') ?? '20');
      return fetchAuditLog({ uuid_sucursal, limit });
    },
    {
      revalidateOnFocus: false,
      onSuccess: (data) => {
        setPageItems(data.items);
        setNextCursor(data.next_cursor);
      },
    },
  );

  const onLoadMore = useCallback(async () => {
    if (nextCursor === null || selected === null) return;
    setIsLoadingMore(true);
    try {
      const next = await fetchAuditLog({
        uuid_sucursal: selected,
        limit: 20,
        cursor: nextCursor,
      });
      setPageItems((prev) => [...prev, ...next.items]);
      setNextCursor(next.next_cursor);
    } finally {
      setIsLoadingMore(false);
    }
  }, [nextCursor, selected]);

  if (selected === null) {
    return (
      <main
        className="flex min-h-screen items-center justify-center bg-background p-4"
        data-testid="page-audit-no-branch"
      >
        <p
          role="status"
          aria-live="polite"
          className="rounded-md border bg-card p-4 text-sm text-muted-foreground shadow-sm"
        >
          {t('audit.noBranchSelected')}
        </p>
      </main>
    );
  }

  const isFirstPageLoading = firstPageSWR.isLoading && pageItems.length === 0;
  const loadMoreError = firstPageSWR.error;

  return (
    <main className="flex min-h-screen flex-col gap-4 bg-background p-4" data-testid="page-audit">
      <header>
        <h1 className="text-2xl font-semibold">{t('audit.title')}</h1>
        <p className="text-sm text-muted-foreground">{t('audit.subtitle')}</p>
      </header>

      <LogTable items={pageItems} isLoading={isFirstPageLoading} error={loadMoreError} />

      {nextCursor !== null && (
        <Button
          type="button"
          variant="outline"
          onClick={() => void onLoadMore()}
          disabled={isLoadingMore}
          data-testid="audit-load-more"
        >
          {isLoadingMore ? t('audit.loadingMore') : t('audit.loadMore')}
        </Button>
      )}
    </main>
  );
}
