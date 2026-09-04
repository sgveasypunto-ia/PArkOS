import { useTranslation } from 'react-i18next';

/**
 * Login — placeholder page.
 *
 * PR10c will wire the actual admin-issuer JWT flow against
 * POST /api/v1/auth/login (parkos_core/api/v1/auth.py).
 * For now this page renders a stub so the route resolves cleanly.
 */
export default function Login() {
  const { t } = useTranslation();
  return (
    <main
      className="flex min-h-screen items-center justify-center bg-background p-4"
      data-testid="page-login"
    >
      <section className="w-full max-w-md space-y-4 rounded-lg border bg-card p-6 text-card-foreground shadow-sm">
        <h1 className="text-2xl font-semibold">{t('app.name')}</h1>
        <p className="text-sm text-muted-foreground">{t('app.tagline')}</p>
        <p className="text-xs text-muted-foreground">
          {t('app.loginPlaceholder')}
        </p>
      </section>
    </main>
  );
}
