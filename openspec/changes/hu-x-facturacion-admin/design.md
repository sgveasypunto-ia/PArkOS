# Design: hu-x-facturacion-admin

> **Change**: `hu-x-facturacion-admin`
> **Phase**: design (sdd-design)
> **Status**: ready for `sdd-tasks` + `sdd-apply`
> **Inputs**: `exploration.md`, `proposal.md`, `specs/facturacion-admin/spec.md` (REQ-X-01..13), `specs/operations/spec.md` (REQ-OPS-200..206 delta)

## 1. Stack alignment

| Capa | Decisión | Rationale |
|---|---|---|
| Framework FE | React 18 + TypeScript strict | ya en uso en `web_admin` |
| Router | `react-router-dom` v6 | mismo que el resto |
| State / cache | SWR (`useSWR` + `mutate`) | ya en uso en `reporteria`, `clientes`, `dian` |
| Forms | `react-hook-form` + Zod resolver | mismo patrón que `ReimprimirTiquete.tsx` (HU-F8.3) y `RenovarSuscripcionDialog.tsx` |
| i18n | `react-i18next` namespace `facturacionAdmin` | mismo patrón que `reporteriaFinanciera`, `dian`, `clientes` |
| UI primitives | shadcn/ui (Card, Badge, Tabs, Dialog, Button, Table, Alert) | ya consumidos |
| Icons | `lucide-react` (`Receipt`, `ExternalLink`, `Printer`, `XCircle`, `AlertCircle`, `FileText`, `Copy`, `RefreshCw`) | ya consumidos en `reporteria/`, `dian/` |
| HTTP client | `parkosFetch` de `@parkos/ui-kit/fetch` con `Idempotency-Key` | ya usado en `electron-sucursal/facturacion/api/facturaApi.ts`; misma abstracción en `web_admin` vía `lib/api/fetchJson` |
| Validation Zod | `zod` v3 | ya en uso |
| Tests | vitest + @testing-library/react + @axe-core/playwright | ya en uso |
| Mocks | `vi.mock('@/features/facturacion/api/facturacionAdminApi')` | mismo patrón que `ReporteriaFinanciera.test.tsx` |

## 2. File structure (new + modified)

### 2.1 Nuevos (frontend)

```
apps/web_admin/src/features/facturacion/
├── api/
│   ├── facturacionAdminApi.ts          (~120 LOC, 5 funciones + 1 type guard)
│   ├── facturacionAdminSchema.ts       (~80 LOC, 5 Zod schemas + 3 error schemas)
│   └── facturacionAdminApi.test.ts     (~150 LOC, 4 tests)
├── hooks/
│   ├── useFacturaDetalle.ts            (~60 LOC, SWR paralelo de 5 endpoints)
│   ├── useReimprimirFactura.ts         (~30 LOC, POST + mutate + toast)
│   ├── useAnularFactura.ts             (~30 LOC, POST + redirect)
│   ├── useCrearReclamoFactura.ts       (~30 LOC, POST + redirect)
│   └── useFacturaHash.ts               (~25 LOC, GET /admin/log-transaccional?uuid_referencia=…)
├── pages/
│   ├── FacturaDetalle.tsx              (~150 LOC, container)
│   └── FacturaDetalle.test.tsx         (~250 LOC, 12 scenarios)
├── components/
│   ├── FacturaHeaderCard.tsx           (~70 LOC)
│   ├── FacturaClienteCard.tsx          (~30 LOC)
│   ├── FacturaItemsTable.tsx           (~50 LOC)
│   ├── FacturaImpuestosTable.tsx       (~50 LOC)
│   ├── FacturaPagosTable.tsx           (~60 LOC, con badges por medio_pago)
│   ├── FacturaElectronicaCard.tsx      (~80 LOC, con retry si rechazado)
│   ├── FacturaEstadoBadge.tsx          (~25 LOC, derivado: vigente|anulada)
│   ├── FacturaAccionesMenu.tsx         (~60 LOC, 3 botones con role-gate)
│   ├── ReimprimirFacturaDialog.tsx     (~50 LOC, RHF + Zod motivo)
│   ├── AnularFacturaDialog.tsx         (~50 LOC, RHF + Zod motivo)
│   ├── ReclamoFacturaDialog.tsx        (~60 LOC, RHF + Zod motivo + descripción)
│   └── FacturaAccionesMenu.test.tsx    (~80 LOC, 1 test: role-gate hide)
└── lib/
    └── estadoFactura.ts                (~25 LOC, derivación V_FACTURA_ESTADO simplificada)
```

### 2.2 Modificados (frontend)

| File | Δ LOC | Cambio |
|---|---|---|
| `apps/web_admin/src/App.tsx` | +2 | `<Route path="/facturacion/:uuid" element={<FacturaDetalle />} />` en grupo global |
| `apps/web_admin/src/features/reporteria/components/FacturasTable.tsx` | +20 | Botón/link "Ver detalle" en cada fila |
| `apps/web_admin/src/features/clientes/components/ClienteFacturasTab.tsx` | +20 | Idem |
| `apps/web_admin/src/pages/HomeHub.tsx` | +10 | Nueva card "Facturación" con icono `Receipt` |
| `apps/web_admin/src/i18n/locales/es-CO.json` | +60 | Namespace `facturacionAdmin` (~30 keys) + `homeHub.cards.facturacion` + `homeHub.cards.facturacionDesc` |
| `apps/web_admin/src/features/reporteria/components/FacturasTable.test.tsx` | +30 | Test del nuevo link |
| `apps/web_admin/src/features/clientes/components/ClienteFacturasTab.test.tsx` | +20 | Idem |
| `apps/web_admin/src/pages/HomeHub.test.tsx` | +10 | Card test (H3 parametrizado ya lo soporta) |

### 2.3 Modificados (backend)

| File | Δ LOC | Cambio |
|---|---|---|
| `backend/packages/parkos_core/src/parkos_core/api/v1/facturacion.py` | +60 | (a) Custom handler para `GET /facturacion/factura-pagos` que reemplaza el factory. (b) Remover el `_mount_factura("factura-pagos", …)` para este recurso. |
| `backend/packages/parkos_core/src/parkos_core/api/v1/facturacion.py` | +20 | Tests del custom handler (4 escenarios de Esc-X-12) |

Total BE: ~80 LOC.

## 3. Backend: custom handler para `GET /facturacion/factura-pagos`

### 3.1 Análisis del bug (causa raíz)

`backend/.../api/router_factory.py:189-255` define `list_endpoint` con signature:

```python
@router.get("", response_model=read_list_schema)
async def list_endpoint(
    cursor: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    ctx: TenantContext = Depends(get_tenant_ctx),
    _claims: None = Depends(issuer_dep),
):
```

**No hay `Query('uuid_factura', ...)`**, por lo que FastAPI descarta
silenciosamente cualquier `?uuid_factura=…` enviado por el cliente.
Verificado con 3 curl en este turno (4 escenarios en la sección 2.4 del
exploration).

El factory tampoco tiene un hook genérico para agregar filtros
per-resource (verificado leyendo `router_factory.py` entero, 430 LOC).
La forma en que otros recursos agregan filtros es reemplazando el
factory por un handler custom (ej. `clientes_cupos.py:118-194`,
`auditoria.py:114-298`).

### 3.2 Approach: custom handler quirúrgico (DEC-X.04)

**NO** se extiende el factory para soportar filtros genéricos (Riesgo X.1: la
extensión genérica impactaría a 49+ recursos). **SÍ** se reemplaza el mount
del factory para `factura-pagos` con un handler custom que:

1. Acepta `uuid_factura: uuid_lib.UUID | None = Query(None)`.
2. Copia la query del factory verbatim (mismo `select(FacturaPagos).order_by(FacturaPagos.created_at.asc(), FacturaPagos.uuid.asc())`).
3. Aplica el WHERE si `uuid_factura` está presente.
4. Aplica el cursor (mismo decode + WHERE que el factory).
5. Aplica el `limit + 1` para detectar `next_cursor`.
6. Serializa con `FacturaPagosRead`.
7. Devuelve `FacturaPagosReadList(items=…, next_cursor=…)`.

Pseudocódigo (en `facturacion.py`):

```python
@router.get(
    "/factura-pagos",
    response_model=FacturaPagosReadList,
    responses={400: {"description": "invalid_cursor"}},
)
async def list_factura_pagos(
    cursor: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    uuid_factura: uuid_lib.UUID | None = Query(None),
    session: AsyncSession = Depends(get_session),
    _ctx: TenantContext = Depends(get_tenant_ctx),
    _claims: None = Depends(_facturacion_issuer_dep),
) -> FacturaPagosReadList:
    try:
        decoded = cursor_decode(cursor) if cursor else None
    except InvalidCursorError as e:
        raise HTTPException(
            status_code=400, detail={"error": "invalid_cursor", "detail": str(e)}
        )
    stmt = select(FacturaPagos).order_by(
        FacturaPagos.created_at.asc(), FacturaPagos.uuid.asc()
    )
    if uuid_factura is not None:
        stmt = stmt.where(FacturaPagos.uuid_factura == uuid_factura)
    if decoded is not None:
        # Misma lógica de cursor que el factory
        cursor_ts = _parse_cursor_timestamp(decoded.created_at)
        stmt = stmt.where(
            (FacturaPagos.created_at < cursor_ts)
            | ((FacturaPagos.created_at == cursor_ts) & (FacturaPagos.uuid > uuid_lib.UUID(decoded.uuid)))
        )
    stmt = stmt.limit(limit + 1)
    with suspend_tenant_context():  # ver §3.3
        result = await session.execute(stmt)
    rows = list(result.scalars().all())
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = cursor_encode(
            Cursor(
                created_at=last.created_at.isoformat(),
                uuid=str(last.uuid),
            )
        )
    return FacturaPagosReadList(
        items=[FacturaPagosRead.model_validate(r) for r in rows],
        next_cursor=next_cursor,
    )
```

### 3.3 Tenant scope (decisión clave)

La tabla `prod.factura_pagos` **NO** tiene `uuid_sucursal` directamente
(verificado: la columna existe per migración 0001 pero la factory no la
filtra por tenant context por default). El tenant scope se aplica a
través de `do_orm_execute` listener (ver `db/tenancy.py`), que filtra
automáticamente cuando el `X-Sucursal-Context` está activo.

**Riesgo**: si el listener no filtra `factura_pagos` correctamente, el
admin cross-branch podría ver pagos de otras sucursales.

**Mitigación**: el handler custom llama `suspend_tenant_context()` para
que el handler explícitamente NO auto-filtrar por X-Sucursal-Context (mismo
patrón que usan los handlers cross-branch de `auditoria.py`), y en su
lugar el tenant scope se aplica via `JOIN con prod.facturas WHERE
prod.facturas.uuid_sucursal IN (admin.sucursales_permitidas)`. Esto es
consistente con `auditoria.py:1170-1180` que hace `JOIN prod.facturas`
para filtrar por `uuid_sucursal` indirectamente.

**Confirmado leyendo el código**:
- `prod.factura_pagos.uuid_sucursal` SÍ existe (columna nullable per
  schema dump de este turno, con default `NULL`).
- El `do_orm_execute` listener filtra automáticamente por
  `ctx.sucursal_uuid` cuando `tenant_scoped=True` (default del factory).
- Como `FacturaPagos` tiene `uuid_sucursal` propio, el listener YA filtra
  por tenant correctamente.

**Por lo tanto, NO se necesita `suspend_tenant_context()`**. El handler
custom hereda el comportamiento del factory (auto-filter via listener).

### 3.4 Tests del fix (4 escenarios de REQ-OPS-203)

`backend/tests/integration/test_factura_pagos_filter.py` (NEW, ~80 LOC):

```python
async def test_factura_pagos_filter_by_uuid_factura_returns_only_matching(session, ...):
    seed factura_pagos(F, ...), seed factura_pagos(F2, ...)
    response = await client.get(
        "/api/v1/facturacion/factura-pagos?uuid_factura={F}",
        headers={"Authorization": f"Bearer {admin_jwt}"},
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert all(i["uuid_factura"] == str(F) for i in items)
    assert len(items) == 1

async def test_factura_pagos_filter_empty_uuid_returns_zero_items(session, ...):
    response = await client.get(
        "/api/v1/facturacion/factura-pagos?uuid_factura=00000000-...",
        headers={"Authorization": f"Bearer {admin_jwt}"},
    )
    assert response.status_code == 200
    assert response.json()["items"] == []

async def test_factura_pagos_no_filter_returns_global_list(session, ...):
    """Backward-compat: sin filter, retorna todo (comportamiento pre-fix)."""
    response = await client.get(
        "/api/v1/facturacion/factura-pagos",
        headers={"Authorization": f"Bearer {admin_jwt}"},
    )
    assert response.status_code == 200
    assert len(response.json()["items"]) > 0

async def test_factura_pagos_filter_with_cursor_pagination(session, ...):
    """Filter se aplica ANTES de la paginación."""
    seed 5 pagos de F
    page1 = await client.get(f"/api/v1/facturacion/factura-pagos?uuid_factura={F}&limit=2")
    assert len(page1.json()["items"]) == 2
    assert page1.json()["next_cursor"] is not None
    page2 = await client.get(f"/api/v1/facturacion/factura-pagos?uuid_factura={F}&limit=2&cursor={page1.json()['next_cursor']}")
    assert len(page2.json()["items"]) == 2
    # No leak de otros facturas
    assert all(i["uuid_factura"] == str(F) for i in page2.json()["items"])
```

## 4. Frontend: container-presentational

### 4.1 `FacturaDetalle.tsx` (container, ~150 LOC)

```tsx
export function FacturaDetalle(): JSX.Element {
  const { uuid } = useParams<{ uuid: string }>();
  const { t } = useTranslation('facturacionAdmin');
  const swr = useFacturaDetalle(uuid ?? null);

  if (swr.header.error) {
    return <FacturaNoEncontrada uuid={uuid} />;
  }
  if (!swr.header.data) {
    return <FacturaDetalleSkeleton />;
  }

  const header = swr.header.data;
  return (
    <article className="mx-auto max-w-4xl space-y-6 p-4" data-testid="factura-detalle">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">
          {t('header.title', { defaultValue: 'Detalle de factura' })}
        </h1>
        <p className="text-sm text-muted-foreground">
          {t('header.subtitle', { defaultValue: 'Investigación transaccional y acciones de admin.' })}
        </p>
      </header>

      <FacturaHeaderCard
        header={header}
        hash={swr.hash.data}
        isLoadingHash={swr.hash.isLoading}
        hashError={swr.hash.error}
        onCopyHash={() => navigator.clipboard.writeText(header.uuid)}
      />

      <FacturaClienteCard />

      <FacturaItemsTable
        items={swr.detalle.data?.items ?? []}
        isLoading={swr.detalle.isLoading}
        error={swr.detalle.error}
        onRetry={() => swr.detalle.mutate()}
      />

      <FacturaImpuestosTable ... />
      <FacturaPagosTable
        pagos={swr.pagos.data?.items ?? []}
        isLoading={swr.pagos.isLoading}
        error={swr.pagos.error}
        onRetry={() => swr.pagos.mutate()}
      />

      <FacturaElectronicaCard
        fe={swr.fe.data}
        isLoading={swr.fe.isLoading}
        error={swr.fe.error}
        onRetry={() => swr.fe.mutate()}
      />

      <FacturaAccionesMenu
        uuid={header.uuid}
        estado={header.estado ?? 'vigente'}
      />
    </article>
  );
}
```

### 4.2 `useFacturaDetalle` (hook, ~60 LOC)

```ts
export function useFacturaDetalle(uuid: string | null) {
  const header = useSWR(
    uuid ? ['factura', uuid] : null,
    () => uuid ? fetchFacturaByUuid(uuid) : null,
    { revalidateOnFocus: false }
  );
  const detalle = useSWR(
    uuid ? ['factura-detalle', uuid] : null,
    () => uuid ? fetchFacturaDetalle(uuid) : null,
    { revalidateOnFocus: false }
  );
  const impuestos = useSWR(
    uuid ? ['factura-impuestos', uuid] : null,
    () => uuid ? fetchFacturaImpuestos(uuid) : null,
    { revalidateOnFocus: false }
  );
  const pagos = useSWR(
    uuid ? ['factura-pagos', uuid] : null,
    () => uuid ? fetchFacturaPagos(uuid) : null,
    { revalidateOnFocus: false }
  );
  const fe = useSWR(
    uuid && header.data?.uuid_factura_electronica
      ? ['factura-electronica', header.data.uuid_factura_electronica]
      : null,
    () => header.data?.uuid_factura_electronica
      ? fetchFacturaElectronicaByUuid(header.data.uuid_factura_electronica)
      : null,
    { revalidateOnFocus: false }
  );
  const hash = useSWR(
    uuid ? ['factura-hash', uuid] : null,
    () => uuid ? fetchFacturaHash(uuid) : null,
    { revalidateOnFocus: false }
  );
  return { header, detalle, impuestos, pagos, fe, hash };
}
```

### 4.3 `facturacionAdminApi.ts` (5 funciones, ~120 LOC)

```ts
export async function fetchFacturaByUuid(uuid: string): Promise<FacturaDetailRead> {
  const raw = await fetchJson<unknown>(
    `/api/v1/facturacion/facturas/${uuid}`,
    { method: 'GET', headers: { Accept: 'application/json' } }
  );
  return FacturaDetailReadSchema.parse(raw);
}

export async function fetchFacturaDetalle(uuidFactura: string): Promise<FacturaDetalleList> {
  const raw = await fetchJson<unknown>(
    `/api/v1/facturacion/factura-detalle?uuid_factura=${uuidFactura}`,
    { method: 'GET', headers: { Accept: 'application/json' } }
  );
  return FacturaDetalleListSchema.parse(raw);
}

// fetchFacturaImpuestos, fetchFacturaPagos, fetchFacturaElectronicaByUuid
// son idénticos en estructura.
```

### 4.4 `facturacionAdminSchema.ts` (~80 LOC, Zod mirrors)

```ts
export const FacturaDetailReadSchema = z.object({
  uuid: z.string().uuid(),
  created_at: z.string(),
  uuid_sucursal: z.string().uuid(),
  subtotal: z.union([z.number(), z.string()]).transform(Number),
  descuento: z.union([z.number(), z.string()]).transform(Number),
  total: z.union([z.number(), z.string()]).transform(Number),
  uuid_ingreso: z.string().uuid().nullable(),
  uuid_salida: z.string().uuid().nullable(),
  uuid_factura_electronica: z.string().uuid().nullable().optional(),
  estado: z.enum(['vigente', 'anulada']).optional(),
});
export type FacturaDetailRead = z.infer<typeof FacturaDetailReadSchema>;

// FacturaDetalleItemSchema, FacturaDetalleListSchema, etc.
```

### 4.5 `FacturaAccionesMenu` (role-gate, ~60 LOC)

```tsx
export function FacturaAccionesMenu({ uuid, estado }: Props): JSX.Element | null {
  const { data: me } = useMe();
  // Server-side check is authority; client-side hide es UX.
  if (!me || me.rol !== 'admin-') return null;

  const [openReimp, setOpenReimp] = useState(false);
  const [openAnular, setOpenAnular] = useState(false);
  const [openReclamo, setOpenReclamo] = useState(false);

  return (
    <div className="flex gap-2" data-testid="factura-acciones-menu">
      <Button onClick={() => setOpenReimp(true)} variant="outline">
        <Printer className="mr-2 h-4 w-4" />
        {t('acciones.reimprimir')}
      </Button>
      {estado === 'vigente' && (
        <Button onClick={() => setOpenAnular(true)} variant="outline">
          <XCircle className="mr-2 h-4 w-4" />
          {t('acciones.anular')}
        </Button>
      )}
      <Button onClick={() => setOpenReclamo(true)} variant="outline">
        <FileText className="mr-2 h-4 w-4" />
        {t('acciones.reclamo')}
      </Button>

      <ReimprimirFacturaDialog uuid={uuid} open={openReimp} onOpenChange={setOpenReimp} />
      <AnularFacturaDialog uuid={uuid} open={openAnular} onOpenChange={setOpenAnular} />
      <ReclamoFacturaDialog uuid={uuid} open={openReclamo} onOpenChange={setOpenReclamo} />
    </div>
  );
}
```

### 4.6 Dialogs (3 dialogs, ~160 LOC total)

Patrón común (ej. `ReimprimirFacturaDialog`):

```tsx
const formSchema = z.object({
  motivo: z.string().min(10, t('dialogs.motivoMinLength', { defaultValue: 'Mínimo 10 caracteres' })),
});
type FormValues = z.infer<typeof formSchema>;

export function ReimprimirFacturaDialog({ uuid, open, onOpenChange }: Props) {
  const { trigger, isMutating } = useReimprimirFactura();
  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: { motivo: '' },
  });
  const onSubmit = async (values: FormValues) => {
    try {
      const result = await trigger(uuid, values.motivo);
      toast.success(t('toasts.reimpresionExitosa', { defaultValue: 'Reimpresión solicitada: ' }) + result.uuid_reimpresion.slice(0, 8));
      form.reset();
      onOpenChange(false);
    } catch (err) {
      toast.error(t('errors.actionFail', { defaultValue: 'No se pudo completar la acción.' }));
    }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('dialogs.reimprimirTitle', { defaultValue: 'Reimprimir factura' })}</DialogTitle>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="motivo"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t('dialogs.motivoLabel', { defaultValue: 'Motivo' })}</FormLabel>
                  <FormControl><Input {...field} placeholder={t('dialogs.motivoPlaceholder', { defaultValue: 'Mínimo 10 caracteres' })} /></FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
                {t('dialogs.cancelar', { defaultValue: 'Cancelar' })}
              </Button>
              <Button type="submit" disabled={isMutating}>
                {isMutating ? '...' : t('dialogs.confirmar', { defaultValue: 'Confirmar' })}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
```

`AnularFacturaDialog` y `ReclamoFacturaDialog` siguen el mismo patrón con campos adicionales (descripción en el caso de reclamo).

## 5. SWR cache invalidation cross-section

Después de cada action, los hooks `use*Factura` llaman
`mutate(swrKey)` para forzar refetch:

- `useReimprimirFactura` → `mutate(['factura', uuid])` + `mutate(['factura-hash', uuid])`.
- `useAnularFactura` → `mutate(['factura', uuid])` + `mutate(['factura-hash', uuid])` + redirect a `/anulaciones/{uuid_anulacion}`.
- `useCrearReclamoFactura` → redirect a `/reclamos/{uuid_reclamo}` (no mutates necesarios — la factura no cambió).

## 6. Idempotency-Key generation

```ts
import { v4 as uuidv4 } from 'uuid'; // o crypto.randomUUID()
function newIdempotencyKey(): string {
  return uuidv4();
}
```

Cada `use*Factura` genera una key fresca por submit y la pasa al
`parkosFetch` (o `fetchJson`) como header `Idempotency-Key: <key>`.
Backend ya respeta el header (PR2).

## 7. i18n

`apps/web_admin/src/i18n/locales/es-CO.json` agrega el namespace
`facturacionAdmin` con las 30+ keys listadas en REQ-X-12. Sin variantes
regionales (sólo es-CO, como el resto del admin).

## 8. Tests

### 8.1 BE (X.1a)
- `backend/tests/integration/test_factura_pagos_filter.py` (NEW): 4 escenarios de REQ-OPS-203.

### 8.2 FE (X.1a)
- `apps/web_admin/src/features/facturacion/api/facturacionAdminApi.test.ts` (NEW, ~150 LOC, 4 tests):
  - `fetchFacturaByUuid` parses response correctamente.
  - `fetchFacturaPagos` agrega `?uuid_factura=...` al query.
  - `fetchFacturaElectronicaByUuid` retorna 404 si no hay FE.
  - Error de red propaga como `ParkosHttpError`.

### 8.3 FE (X.1b)
- `apps/web_admin/src/features/facturacion/pages/FacturaDetalle.test.tsx` (NEW, ~250 LOC, 12 escenarios):
  - 1: renderiza skeleton mientras header carga.
  - 2: renderiza header + 6 secciones con datos mock.
  - 3: 404 del header → muestra "Factura no encontrada".
  - 4: 404 del FE → muestra "FE no generada" sin tapar el resto.
  - 5: error de detalle → alert inline en items, no fatal.
  - 6: tenant scope cross-branch → 404 (mock).
  - 7: copy-to-clipboard del hash.
  - 8: copy-to-clipboard del uuid.
  - 9: formatea números con separadores es-CO.
  - 10: format de fecha con timezone local.
  - 11: badge de estado con texto + color (axe-core implícito).
  - 12: renderiza el `FacturaAccionesMenu` si rol=admin-.

- `apps/web_admin/src/features/facturacion/components/FacturaAccionesMenu.test.tsx` (NEW, ~80 LOC, 1 test):
  - renderiza 3 botones si rol=admin-.
  - renderiza null si rol=operador-.

### 8.4 FE (X.2)
- `FacturasTable.test.tsx` (+30 LOC, 1 test): click en "Ver detalle" navega.
- `ClienteFacturasTab.test.tsx` (+20 LOC, 1 test): idem.

### 8.5 FE (X.3..X.5)
- `ReimprimirFacturaDialog.test.tsx` (~80 LOC, 3 tests).
- `AnularFacturaDialog.test.tsx` (~80 LOC, 3 tests).
- `ReclamoFacturaDialog.test.tsx` (~100 LOC, 4 tests).

### 8.6 FE (X.6)
- `HomeHub.test.tsx` (+10 LOC, 1 test): card visible + link a `/reporteria/financiera`.

### 8.7 a11y (X.7)
- `FacturaDetalle.a11y.test.tsx` (NEW, ~30 LOC, 1 test): axe-core scan, 0 violations WCAG 2.1 AA.

## 9. Migration / schema

**NO hay schema change**. Las 3 actions son append-only sobre tablas
existentes. El fix del factory es un handler custom sin migración.

## 10. Validation matrix

| Layer | Validator | Threshold |
|---|---|---|
| BE unit + integration | `pytest backend/tests` con testcontainers | REQ-OPS-203: 4 new tests green; total 14 nuevos; coverage ≥80% en el custom handler |
| BE lint | `ruff check` + `mypy --strict` | 0 errors |
| FE unit | `pnpm --filter @apps/web_admin vitest run` | 18 new scenarios green (4 api + 12 detalle + 1 acciones + 1 homehub + 3 dialogs + 1 a11y) |
| FE types + lint | `tsc --noEmit` + `eslint` | 0 errors |
| a11y | `@axe-core/playwright` en `FacturaDetalle` | 0 WCAG 2.1 AA violations |
| schema drift | `python openspec/scripts/check_schema_match.py` | exits `0`; no migration |

## 11. Rollback strategy

Cada PR se puede revertir individualmente. Si X.1a (BE fix) falla:
- Rollback del handler custom + restaurar el `_mount_factura('factura-pagos', ...)` del factory. La página de detalle (X.1b) se queda con `fetchFacturaPagos` que sigue funcionando pero muestra los pagos de todas las facturas (degradación graceful, no crash).

Si X.1b (página) falla:
- Rollback del route + componentes. Las 3 actions (X.3..X.5) ya no tienen dialogs pero los endpoints siguen accesibles vía API.
- Drill-down desde listas (X.2) no apunta a nada roto.

Si X.6 (HomeHub card) falla:
- Rollback trivial. La card no es crítica.

## 12. Open follow-ups (no en este change)

- HU-X.8: listado standalone `/facturacion` con búsqueda global.
- Endpoint display enriquecido (`GET /admin/facturacion/facturas/{uuid}/display`) que retorne el shape F8.4 (cliente, sucursal, vehiculo). Hoy el drill-down muestra "Consumidor final" para todas.
- Reintento FE: la página de detalle ya tiene el botón "Reintentar" si FE está `rechazado`, pero no polling realtime. Si se quiere, abrir un HU con WebSocket o SSE.
- Extender el filter `?uuid_factura=...` a los otros 3 endpoints (`factura-detalle`, `factura-impuestos`, `factura-otros-cobros`). Hoy la página hace 5 calls separados; con el filter, podría ser 1 con JOINs. Trade-off: complejidad vs latencia.
- Reemplazar el factory `make_router` con uno que soporte filtros per-resource (Riesgo X.1). 80 LOC + tests. Cambio cross-cutting que toca 49+ recursos.
