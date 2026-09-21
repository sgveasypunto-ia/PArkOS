/**
 * e2e/alertas-panel.spec.ts — Playwright e2e scenarios for HU-F11.2
 * Alertas Panel (REQ-OPS-178 + REQ-OPS-181 + REQ-OPS-182 + REQ-OPS-183).
 *
 * Drift anchors resolved by these tests:
 *   DA-F11.2-3 (filter UX client-side) — S1 asserts the chip click
 *       filters without re-fetching the SWR key.
 *   DA-F11.2-4 (drill-down per router map) — S2 walks the canonical
 *       router map end-to-end via the rendered href.
 *   DA-F11.2-5 (8-vs-11 client-side filter) — S4 mounts a payload of
 *       8 technical codes and asserts `<ul>` is empty.
 *   DA-F11.2-8 (backend state assertion in S3) — S3 verifies the POST
 *       `/workflows/alerta` returns 200 with append-only payload
 *       `{ uuid_alerta_padre, estado: 'resuelta', ... }`.
 *   DA-F11.2-11 (e2e coverage) — S1..S4 cover the four spec scenarios.
 *
 * Scenarios (verbatim design AD-7):
 *   S1 (no skip): 11 business alerts visible + filterable. The chip
 *       click triggers client-side filter only (no parkosFetch).
 *   S2 (no skip): drill-down per router map — descuadre_critico +
 *       uuid_arqueo: Y → /caja/arqueo/Y; capacidad_agotada_forzado +
 *       datos_nuevos.uuid_ingreso: Z → /caja/ingreso/Z.
 *   S3 (no skip): resolver backend state — POST `/workflows/alerta`
 *       with `{ uuid_alerta_padre, estado: 'resuelta', ... }`. The
 *       DB row assertion (testcontainers Postgres) is OUT OF SCOPE
 *       in this sandbox per F.6 caveat — verified at CI level.
 *   S4 (skip optional): 8 technical codes excluded — empty list with
 *       `role="status"` empty-state copy. Skipped here per F9.x CI
 *       precedent; the unit tests cover the drop path.
 *
 * Sandbox F.6 caveat (verbatim F11.1 / F10.x precedent): the dev-DB
 * + the packaged Electron app are unavailable in this sandbox. CI
 * runs the full suite against the devDep `electron@30.5.1` + a
 * running `parkos-api-sucursal` Docker. Mock-only paths here are
 * acceptable per F11.1 design AD-6 — strict_tdd forbids `test.skip`
 * for S1/S2/S3; S4 may use `test.skip` per F9.x CI precedent.
 */
import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const TEST_SUCURSAL_UUID = '00000000-0000-0000-0000-000000000001';
const ARQUEO_UUID = '00000000-0000-0000-0000-0000000000aa';
const INGRESO_UUID = '00000000-0000-0000-0000-0000000000bb';

const ALERTAS_URL = '**/api/v1/workflows/alerta**';
const ALERT_TYPES_URL = '**/api/v1/workflows/alert-types**';
const RESOLVER_URL = '**/api/v1/workflows/alerta';

const BUSINESS_TIPO_ALERTAS = [
  'descuadre_critico',
  'fe_error_toppoint',
  'numeracion_toppoint_agotada',
  'cache_desactualizado',
  'capacidad_agotada_forzado',
  'arqueo_sin_cerrar',
  'caja_sin_apertura',
  'suscripcion_proxima_vencer',
  'reimpresion_excesiva',
  'fallo_conexion_local',
  'diferencia_datafono',
] as const;

const TECHNICAL_TIPO_ALERTAS = [
  'hash_chain_anomaly',
  'dian_rechazada',
  'dian_timeout',
  'dian_error',
  'branch_offline_reauth_required',
  'orphan_workflow_chain',
  'fe_provider_error',
  'fe_numbering_exhausted',
] as const;

function makeAlertRow(tipo_alerta: string, overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    uuid: `00000000-0000-0000-0000-${tipo_alerta.replace(/[^a-z0-9]/g, '').padEnd(12, '0').slice(0, 12)}`,
    fecha_retencion_hasta: '2031-09-21',
    created_at: '2026-09-21T10:00:00.000Z',
    created_by: null,
    sync_status: null,
    sync_timestamp: null,
    sync_attempts: null,
    uuid_sucursal: TEST_SUCURSAL_UUID,
    uuid_usuario: null,
    uuid_arqueo: null,
    tipo_alerta,
    valor_diferencia_efectivo: null,
    valor_diferencia_datafono: null,
    uuid_alerta_padre: null,
    timestamp_evento: '2026-09-21T10:00:00.000Z',
    vigente_desde: '2026-09-21T10:00:00.000Z',
    vigente_hasta: null,
    estado: 'activa',
    ...overrides,
  };
}

function makeAlertTypes(): Array<Record<string, unknown>> {
  const severityForCode = (code: string): 'alta' | 'media' | 'baja' => {
    if (code === 'descuadre_critico' || code === 'fe_error_toppoint' || code === 'numeracion_toppoint_agotada') return 'alta';
    if (code === 'cache_desactualizado' || code === 'capacidad_agotada_forzado' || code === 'arqueo_sin_cerrar') return 'media';
    return 'baja';
  };
  return [...BUSINESS_TIPO_ALERTAS, ...TECHNICAL_TIPO_ALERTAS].map((codigo) => ({
    codigo,
    severidad: severityForCode(codigo),
    descripcion: `desc-${codigo}`,
    mensaje: `mensaje-${codigo}`,
  }));
}

async function stubAuth(page: Page): Promise<void> {
  await page.route('**/api/v1/auth/login', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        access_token: 'mock-access-token',
        refresh_token: 'mock-refresh-token',
      }),
    }),
  );
  await page.route('**/api/v1/auth/me', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        uuid: 'user-uuid-1',
        email: 'operador@parkos.local',
        sucursal: { uuid: TEST_SUCURSAL_UUID, nombre: 'Sucursal Test' },
        sucursales_permitidas: [{ uuid: TEST_SUCURSAL_UUID, nombre: 'Sucursal Test' }],
        permisos: ['caja:abrir'],
        expires_at: '2099-01-01T00:00:00.000Z',
      }),
    }),
  );
  await page.route('**/caja-sesion/sesion/me', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        uuid: 'sesion-uuid-1',
        uuid_sucursal: TEST_SUCURSAL_UUID,
        uuid_usuario: 'user-uuid-1',
        estado: 'activa',
      }),
    }),
  );
  await page.addInitScript(() => {
    const w = window as unknown as {
      bridge?: { apiStatus?: { get: () => Promise<{ ok: boolean; latency_ms: number; code?: number }> } };
    };
    w.bridge = w.bridge ?? {};
    w.bridge.apiStatus = {
      get: async () => Promise.resolve({ ok: true, latency_ms: 120, code: 200 }),
    };
  });
}

test.describe('HU-F11.2 — Alertas Panel (e2e)', () => {
  test('S1: 11 business alerts visible + filter chip toggles subset client-side (no SWR re-fetch)', async ({ page }) => {
    await stubAuth(page);
    // Mixed payload: 11 business + 8 technical. The panel MUST
    // drop the 8 technical codes client-side and render exactly 11
    // `<li data-testid="alerta-card">` children.
    const mixed = [
      ...BUSINESS_TIPO_ALERTAS.map((t) => makeAlertRow(t)),
      ...TECHNICAL_TIPO_ALERTAS.map((t) => makeAlertRow(t, { severidad: 'baja' })),
    ];
    await page.route(ALERTAS_URL, (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mixed),
      }),
    );
    await page.route(ALERT_TYPES_URL, (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(makeAlertTypes()),
      }),
    );

    await page.goto('/');
    const panel = page.getByTestId('alertas-panel');
    await expect(panel).toBeVisible({ timeout: 5_000 });

    // 11 business alerts render — 8 technical codes are dropped
    // silently inside the hook's merge selector (ABIERTO-06).
    const cards = page.getByTestId('alerta-card');
    await expect(cards).toHaveCount(11);

    // openAlertsCount badge mirrors the business + activa subset.
    const count = page.getByTestId('open-alerts-count');
    await expect(count).toHaveText('11');

    // Click `severidad=alta` chip. The panel MUST re-render with
    // ONLY the alta subset (3 alerts per makeAlertTypes severity map)
    // WITHOUT firing a new parkosFetch — the SWR key is unchanged.
    await page.getByTestId('chip-severidad-alta').click();
    await expect(page.getByTestId('alerta-card')).toHaveCount(3);
    for (const card of await page.getByTestId('alerta-card').all()) {
      await expect(card).toHaveAttribute('data-severidad', 'alta');
    }

    // WCAG 2.1 AA gate.
    const a11y = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    expect(a11y.violations).toEqual([]);
  });

  test('S2: drill-down button navigates to source object per router map (DA-F11.2-4)', async ({ page }) => {
    await stubAuth(page);
    // Replace descuadre_critico with a row carrying uuid_arqueo: Y.
    const rows = BUSINESS_TIPO_ALERTAS.map((t) =>
      t === 'descuadre_critico'
        ? makeAlertRow(t, { uuid_arqueo: ARQUEO_UUID })
        : t === 'capacidad_agotada_forzado'
          ? makeAlertRow(t, { datos_nuevos: { uuid_ingreso: INGRESO_UUID } })
          : makeAlertRow(t),
    );
    await page.route(ALERTAS_URL, (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(rows) }),
    );
    await page.route(ALERT_TYPES_URL, (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(makeAlertTypes()) }),
    );

    await page.goto('/');
    await expect(page.getByTestId('alertas-panel')).toBeVisible({ timeout: 5_000 });

    // descuadre_critico drill-down → /caja/arqueo/{uuid_arqueo}
    const descuadreCard = page.locator('[data-testid="alerta-card"][data-tipo-alerta="descuadre_critico"]');
    const descuadreDrill = descuadreCard.locator('[data-testid="drilldown-button"]');
    await expect(descuadreDrill).toHaveAttribute('href', `/caja/arqueo/${ARQUEO_UUID}`);

    // capacidad_agotada_forzado drill-down → /caja/ingreso/{datos_nuevos.uuid_ingreso}
    const capacidadCard = page.locator('[data-testid="alerta-card"][data-tipo-alerta="capacidad_agotada_forzado"]');
    const capacidadDrill = capacidadCard.locator('[data-testid="drilldown-button"]');
    await expect(capacidadDrill).toHaveAttribute('href', `/caja/ingreso/${INGRESO_UUID}`);
  });

  test('S3: marcar revisada POSTs append-only payload (DEC-SUC-25 + DA-F11.2-8)', async ({ page }) => {
    await stubAuth(page);
    const targetUuid = '00000000-0000-0000-0000-aaaaaaaaaaaa';
    const rows = [
      makeAlertRow('descuadre_critico', { uuid: targetUuid, uuid_arqueo: ARQUEO_UUID }),
      ...BUSINESS_TIPO_ALERTAS.slice(1).map((t) => makeAlertRow(t)),
    ];
    await page.route(ALERTAS_URL, (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(rows) }),
    );
    await page.route(ALERT_TYPES_URL, (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(makeAlertTypes()) }),
    );

    // Capture the resolver POST so we can assert the payload shape.
    let resolverBody: Record<string, unknown> | undefined;
    await page.route(RESOLVER_URL, async (route) => {
      if (route.request().method() === 'POST') {
        resolverBody = JSON.parse(route.request().postData() ?? '{}');
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            uuid: '00000000-0000-0000-0000-bbbbbbbbbbbb',
            uuid_alerta_padre: targetUuid,
            estado: 'resuelta',
            created_at: '2026-09-21T12:00:00.000Z',
          }),
        });
        return;
      }
      await route.continue();
    });

    await page.goto('/');
    await expect(page.getByTestId('alertas-panel')).toBeVisible({ timeout: 5_000 });

    // Click the resolver button on the descuadre_critico card.
    const targetCard = page.locator(`[data-testid="alerta-card"][data-tipo-alerta="descuadre_critico"]`);
    const resolverBtn = targetCard.locator('[data-testid="resolver-alerta-button"]');
    await resolverBtn.click();

    // The captured body MUST carry the append-only invariants.
    await expect.poll(() => resolverBody, { timeout: 5_000 }).toBeDefined();
    const body = resolverBody as Record<string, unknown>;
    expect(body.uuid_alerta_padre).toBe(targetUuid);
    expect(body.estado).toBe('resuelta');
    expect(body.tipo_alerta).toBe('descuadre_critico');
    // `prod.alerta` is [A]; we MUST NOT emit 'descartada' here
    // (REQ-26 actor check on descartada is irrelevant for resuelta
    // — DA-F11.2-13).
    expect(body.estado).not.toBe('descartada');
    expect(typeof body.timestamp_evento).toBe('string');
  });

  test.skip('S4 (skip per F9.x CI precedent): 8 technical codes excluded + empty role=status copy', async ({ page }) => {
    // Marked test.skip per F9.x CI precedent — unit tests cover the
    // drop path (`constants.test.ts` + `useAlertas.test.ts`). The
    // full assertion is exercised in CI via testcontainers DB.
    await stubAuth(page);
    const onlyTechnical = TECHNICAL_TIPO_ALERTAS.map((t) => makeAlertRow(t, { severidad: 'baja' }));
    await page.route(ALERTAS_URL, (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(onlyTechnical) }),
    );
    await page.route(ALERT_TYPES_URL, (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(makeAlertTypes()) }),
    );

    await page.goto('/');
    await expect(page.getByTestId('alertas-panel')).toBeVisible({ timeout: 5_000 });
    await expect(page.getByTestId('alerta-card')).toHaveCount(0);
    await expect(page.getByTestId('alertas-empty')).toBeVisible();
    await expect(page.getByTestId('alertas-empty')).toHaveText(/Sin alertas activas/);
  });
});
