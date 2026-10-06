/**
 * `<Perfil />` — placeholder page for the operator's own profile.
 *
 * Route: `/perfil`. Lives in the global authed group (no `RequireSucursal`
 * gate) so it is reachable before the operator picks a branch. The
 * `<TopNav />` is the surrounding chrome, just like `/` and `/catalogos`.
 *
 * WHY PLACEHOLDER:
 *   The `<TopNav />` dropdown's "Mi perfil" item has to land SOMEWHERE.
 *   Wiring it to a real profile-management surface (avatar upload, name
 *   editing, password change) is a real feature with its own
 *   backend, schema, and tests. For now we show the immutable identity
 *   the admin already has in `useAdminAuth()` so the flow is closed and
 *   the placeholder can grow into the real page without a route rename.
 *
 * WHY THIS FILE LIVES AT `pages/Perfil.tsx` AND NOT
 * `features/auth/pages/Perfil.tsx`:
 *   `pages/` is the surface-level route landing. The feature slices
 *   (admin, catalogos, etc.) own their own domain. Profile IS the
 *   operator's own identity, not a feature — it sits at the same level
 *   as `Dashboard`, `HomeHub`, `SeleccionarSucursal`.
 */
import { useTranslation } from 'react-i18next';
import { useAdminAuth } from '@parkos/ui-kit/hooks';
import { ArrowLeft } from 'lucide-react';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useGoBack } from '@/lib/useGoBack';

interface ProfileRow {
  labelKey: string;
  value: string;
  fallback: string;
  testId: string;
}

export default function Perfil(): JSX.Element {
  const { t } = useTranslation();
  const { user, rol, sucursalUuids } = useAdminAuth();
  // PT-1: back to the screen the user came from; '/' only as a deep-link fallback.
  const goBack = useGoBack('/');

  const email = user?.email ?? '';
  const uuid = user?.uuid ?? '';

  const rows: ProfileRow[] = [
    {
      labelKey: 'perfil.row.email',
      value: email,
      fallback: '—',
      testId: 'perfil-row-email',
    },
    {
      labelKey: 'perfil.row.rol',
      value: rol ?? '',
      fallback: '—',
      testId: 'perfil-row-rol',
    },
    {
      labelKey: 'perfil.row.uuid',
      value: uuid,
      fallback: '—',
      testId: 'perfil-row-uuid',
    },
    {
      labelKey: 'perfil.row.sucursales',
      value: String(sucursalUuids.length),
      fallback: '0',
      testId: 'perfil-row-sucursales',
    },
  ];

  return (
    <div className="mx-auto max-w-2xl px-4 py-10" data-testid="page-perfil">
      <header className="mb-6">
        <button
          type="button"
          onClick={goBack}
          className="text-muted-foreground focus-ring inline-flex items-center gap-1.5 text-sm hover:text-foreground"
          data-testid="perfil-back"
        >
          <ArrowLeft className="size-4" aria-hidden="true" />
          {t('perfil.back', 'Volver')}
        </button>
        <h1 className="mt-4 text-2xl font-semibold tracking-tight">
          {t('perfil.title', 'Mi perfil')}
        </h1>
        <p className="text-muted-foreground mt-1 text-sm">
          {t('perfil.subtitle', 'Datos de tu cuenta.')}
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle>{t('perfil.identity', 'Identidad')}</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="divide-border grid grid-cols-1 divide-y text-sm">
            {rows.map((row) => (
              <div
                key={row.labelKey}
                data-testid={row.testId}
                className="grid grid-cols-3 gap-3 py-3"
              >
                <dt className="text-muted-foreground">{t(row.labelKey, row.fallback)}</dt>
                <dd className="col-span-2 break-all font-mono text-xs sm:text-sm">
                  {row.value.length > 0 ? row.value : row.fallback}
                </dd>
              </div>
            ))}
          </dl>
        </CardContent>
      </Card>
    </div>
  );
}
