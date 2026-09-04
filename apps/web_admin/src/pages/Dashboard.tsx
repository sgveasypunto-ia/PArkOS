import { useTranslation } from 'react-i18next';

/**
 * Dashboard — placeholder for the multi-tenant admin landing page.
 *
 * PR10c will mount the BranchSelector on top of this layout once
 * the /api/v1/admin/me endpoint is wired into the React Query client
 * (see tasks.md T-PR10-10..T-PR10-13).
 */
export default function Dashboard() {
  const { t } = useTranslation();
  return (
    <main
      className="flex min-h-screen items-center justify-center bg-background p-4"
      data-testid="page-dashboard"
    >
      <section className="w-full max-w-2xl space-y-3 rounded-lg border bg-card p-8 text-card-foreground shadow-sm">
        <h1 className="text-3xl font-bold tracking-tight">
          {t('app.dashboard')}
        </h1>
        <p className="text-sm text-muted-foreground">{t('app.tagline')}</p>
        <p className="text-xs text-muted-foreground">
          {t('app.bootstrapNotice')}
        </p>
      </section>
    </main>
  );
}
