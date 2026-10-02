/**
 * `<ClienteSuscripciones />` — tab "Suscripciones" de `ClienteDetalle`
 * (HU-F20.1).
 *
 * "Vigentes": the plain `subscripciones-cliente` list already returns
 * only `vigente_hasta IS NULL` rows (`router_factory.py`'s
 * `list_endpoint`), so filtering that by `uuid_cliente` client-side
 * (shared with `ClienteVehiculosTab.tsx` via
 * `listSubscripcionesClienteByCliente` in `api/clientesApi.ts`) is all
 * "vigentes" needs.
 *
 * "Históricas": per plan.md, fetched via
 * `GET /subscripciones-cliente/{uuid}/history`. IMPORTANT CAVEAT found
 * while wiring this (documented in depth on
 * `getSubscripcionClienteHistory`'s own docstring in `clientesApi.ts`):
 * `router_factory.py`'s generic history endpoint filters by
 * `model_cls.uuid == :uuid` (the single-column PK), and
 * `close_and_insert` REGENERATES `uuid` on every bi-temporal version --
 * so a CURRENT row's uuid (the only uuid this tab ever has, since the
 * vigentes list only returns current rows) can only ever match that ONE
 * row. It can never surface a PRIOR closed version, whose uuid is never
 * learned anywhere in this UI. `tarifasApi.ts` hit the identical gap and
 * got a dedicated "by-key" endpoint (PR-C v2); `subscripciones-cliente`
 * has no equivalent today. This tab still calls `/history` per the
 * planned contract (so the wiring is correct and future-proof once/if a
 * by-key endpoint ships), but in practice "Históricas" will show at most
 * the same single row as "Vigentes" until that backend gap closes --
 * flagged here and in the HU-F20.1 report, not fixed in this change
 * (`router_factory.py` is explicitly shared/out-of-scope).
 */
import { useTranslation } from 'react-i18next';
import useSWR from 'swr';

import { Badge } from '@/components/ui/badge';
import { diasParaVencer } from '@/lib/subscripciones';

import {
  getSubscripcionClienteHistory,
  listSubscripcionesClienteByCliente,
  type SubscripcionCliente,
} from '../api/clientesApi';

export interface ClienteSuscripcionesProps {
  uuidCliente: string;
}

function ordenarDescendente(items: SubscripcionCliente[]): SubscripcionCliente[] {
  return [...items].sort((a, b) => (a.vigente_desde < b.vigente_desde ? 1 : -1));
}

export function ClienteSuscripciones({ uuidCliente }: ClienteSuscripcionesProps): JSX.Element {
  const { t } = useTranslation();

  const { data, error, isLoading } = useSWR<{
    vigentes: SubscripcionCliente[];
    historicas: SubscripcionCliente[];
  }>(
    `/clientes/${uuidCliente}/suscripciones`,
    async () => {
      const vigentes = await listSubscripcionesClienteByCliente(uuidCliente);
      const historicasPorSuscripcion = await Promise.all(
        vigentes.map((s) => getSubscripcionClienteHistory(s.uuid)),
      );
      return {
        vigentes: ordenarDescendente(vigentes),
        historicas: ordenarDescendente(historicasPorSuscripcion.flat()),
      };
    },
    { revalidateOnFocus: false },
  );

  if (isLoading) {
    return (
      <p
        role="status"
        aria-live="polite"
        data-testid="cliente-suscripciones-loading"
        className="text-sm text-muted-foreground"
      >
        {t('common.loading', 'Cargando…')}
      </p>
    );
  }

  if (error) {
    return (
      <p
        role="alert"
        aria-live="assertive"
        data-testid="cliente-suscripciones-error"
        className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
      >
        {t('clienteSuscripciones.error', 'No se pudieron cargar las suscripciones.')}
      </p>
    );
  }

  const vigentes = data?.vigentes ?? [];
  const historicas = data?.historicas ?? [];

  return (
    <div className="space-y-6">
      <section
        aria-label={t('clienteSuscripciones.vigentesLabel', 'Suscripciones vigentes')}
        data-testid="cliente-suscripciones-vigentes"
      >
        <h3 className="mb-2 text-sm font-semibold">
          {t('clienteSuscripciones.vigentes', 'Vigentes')}
        </h3>
        {vigentes.length === 0 ? (
          <p
            role="status"
            data-testid="cliente-suscripciones-vigentes-empty"
            className="text-sm text-muted-foreground"
          >
            {t('clienteSuscripciones.vigentesEmpty', 'Sin suscripciones vigentes.')}
          </p>
        ) : (
          <ol className="space-y-2">
            {vigentes.map((s) => {
              const dias = diasParaVencer(s.fecha_vencimiento);
              return (
                <li
                  key={s.uuid}
                  data-testid={`cliente-suscripcion-vigente-${s.uuid}`}
                  className="rounded-lg border bg-card px-4 py-3 text-sm"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span>
                      {t('clienteSuscripciones.rango', '{{inicio}} → {{vencimiento}}', {
                        inicio: s.fecha_inicio_cobertura ?? '—',
                        vencimiento: s.fecha_vencimiento ?? '—',
                      })}
                    </span>
                    {dias !== null && (
                      <Badge
                        variant={dias < 0 ? 'destructive' : 'secondary'}
                        data-testid={`cliente-suscripcion-dias-${s.uuid}`}
                      >
                        {dias >= 0
                          ? t('clienteSuscripciones.venceEn', 'vence en {{dias}} días', { dias })
                          : t('clienteSuscripciones.vencidaHace', 'vencida hace {{dias}} días', {
                              dias: Math.abs(dias),
                            })}
                      </Badge>
                    )}
                  </div>
                  <p className="text-muted-foreground text-xs">{s.estado}</p>
                </li>
              );
            })}
          </ol>
        )}
      </section>

      <section
        aria-label={t('clienteSuscripciones.historicasLabel', 'Suscripciones históricas')}
        data-testid="cliente-suscripciones-historicas"
      >
        <h3 className="mb-2 text-sm font-semibold">
          {t('clienteSuscripciones.historicas', 'Históricas')}
        </h3>
        {historicas.length === 0 ? (
          <p
            role="status"
            data-testid="cliente-suscripciones-historicas-empty"
            className="text-sm text-muted-foreground"
          >
            {t('clienteSuscripciones.historicasEmpty', 'Sin versiones históricas registradas.')}
          </p>
        ) : (
          <ol className="space-y-2">
            {historicas.map((s) => (
              <li
                key={s.uuid}
                data-testid={`cliente-suscripcion-historica-${s.uuid}`}
                className="rounded-lg border bg-muted/30 px-4 py-3 text-sm"
              >
                <span>
                  {t('clienteSuscripciones.rango', '{{inicio}} → {{vencimiento}}', {
                    inicio: s.fecha_inicio_cobertura ?? '—',
                    vencimiento: s.fecha_vencimiento ?? '—',
                  })}
                </span>
                <p className="text-muted-foreground text-xs">{s.estado}</p>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}
