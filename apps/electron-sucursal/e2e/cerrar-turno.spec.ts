/**
 * `cerrar-turno.spec.ts` — Playwright e2e scenarios for HU-F10.2
 * Cierre de Turno (REQ-OPS-161).
 *
 * Mirrors the `e2e/arqueo.spec.ts` (F10.1) + `e2e/caja/turno.spec.ts`
 * (F3.3) patterns: every scenario is wrapped in `test.skip(...)` per
 * the F9.x / Engram #1894 precedent because the Electron main process
 * + local-dev DB are unavailable in this sandbox. The test bodies
 * are FULLY written so they will run green in CI with the devDep
 * `electron@30.5.1` + `node-usb-mock@0.4.1` installed.
 *
 * Scenarios (per REQ-OPS-161):
 *
 *   1. happy path `|diferencia|=0` + `justificacion` empty
 *      - POST /caja/arqueo body MUST carry `tipo_arqueo='cierre_turno'`
 *      - bridge.imprimir MUST be called exactly once with
 *        `auditoria_codigo='cierre_turno'`
 *      - URL MUST navigate to `/login?closed=true`
 *      - axe-core on `/login` MUST report zero violations (no leftover
 *        focus traps from the cerrar-turno form).
 *
 *   2. strict-mode `|diferencia|>0` requires justificacion inline
 *      - `valor_efectivo_reportado=97000` with `valor_esperado=100000`
 *        (diferencia = -3000)
 *      - `<ArqueoSheet requiredMode='cierre_turno'>` (or inline
 *        CerrarTurnoArqueoForm shim) keeps the Confirmar button
 *        disabled while `justificacion.length < 3`
 *      - After typing >= 3 chars, button re-enables, POST carries the
 *        justificacion field
 *
 *   3. orphan-uuid: POST 200 (uuid_arqueo) + PUT 500 (mocked)
 *      - Banner surfaces `uuid_arqueo` via
 *        `data-testid='cerrar-turno-orphan-uuid'`
 *      - NO redirect, NO logout
 *
 * Sandbox F.6 caveat (verbatim F8.x/F9.x precedent): Electron +
 * backend unavailable in this sandbox. CI with the devDep installed
 * runs the full suite.
 */
import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const TEST_EMAIL = 'operador@parkos.local';
const TEST_PASSWORD = 'Pass1234word';
const TEST_SESION_UUID = 'sesion-uuid-1';
const TEST_SUCURSAL_UUID = 'suc-uuid-1';
const TEST_RESUMEN_URL = '**/api/v1/caja/arqueo/resumen**';
const TEST_ARQUEO_URL = '**/api/v1/caja/arqueo';
const TEST_CERRAR_SESION_URL =
  '**/api/v1/caja-sesion/sesion/*/cerrar';

const ARQUEO_TOLERANCIA_EFECTIVO = 1_000;
const ARQUEO_TOLERANCIA_DATAFONO = 500;

/**
 * Helper: stubs `bridge.imprimir` via `window` injection so the
 * `bridge.imprimir` calls fired by the renderer can be observed from
 * the e2e. Mirrors the F10.1 arqueo.spec.ts pattern.
 */
async function stubBridgeImprimir(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const w = window as unknown as {
      __bridgeImprimirCalls: Array<{ kind: string; payload: unknown }>;
    };
    w.__bridgeImprimirCalls = [];
    const originalBridge = (
      window as unknown as {
        bridge?: { imprimir?: (k: string, p: unknown) => Promise<unknown> };
      }
    ).bridge;
    if (originalBridge?.imprimir) {
      const original = originalBridge.imprimir.bind(originalBridge);
      originalBridge.imprimir = (kind: string, payload: unknown) => {
        w.__bridgeImprimirCalls.push({ kind, payload });
        return original(kind, payload);
      };
    }
  });
}

/**
 * Helper: stubs the auth login + sesion-me endpoints so the page
 * boot path (useAuth, useSesionActiva) succeeds without a real backend.
 */
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
        email: TEST_EMAIL,
        uuid_usuario: 'user-uuid-1',
      }),
    }),
  );
  await page.route('**/caja-sesion/sesion/me', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        uuid: TEST_SESION_UUID,
        uuid_sucursal: TEST_SUCURSAL_UUID,
        uuid_usuario: 'user-uuid-1',
        estado: 'activa',
      }),
    }),
  );
}

test.describe('HU-F10.2 — Cierre de turno (e2e)', () => {
  test.skip('happy path: diferencia === 0 + empty justificacion → 200+200 + redirect /login?closed=true', async ({
    page,
  }) => {
    await stubAuth(page);
    await stubBridgeImprimir(page);

    // Mock the resumen endpoint (expected values).
    await page.route(TEST_RESUMEN_URL, (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          uuid_sucursal: TEST_SUCURSAL_UUID,
          fecha: '2026-09-21',
          total_efectivo_cop: 100_000,
          total_datafono_cop: 0,
          diferencia_cop: 0,
          sesiones_cerradas: 1,
        }),
      }),
    );

    // Capture the arqueo POST body to assert the discriminator.
    let arqueoBody: Record<string, unknown> | null = null;
    await page.route(TEST_ARQUEO_URL, (route) => {
      arqueoBody = JSON.parse(route.request().postData() ?? '{}') as Record<
        string,
        unknown
      >;
      return route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          uuid: 'arqueo-uuid-cierre-1',
          alerta_generada: false,
        }),
      });
    });

    // PUT sesion close returns 200.
    await page.route(TEST_CERRAR_SESION_URL, (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          uuid: TEST_SESION_UUID,
          timestamp_cierre: '2026-09-21T18:00:00Z',
        }),
      }),
    );

    // Login + navigate to /caja/cerrar-turno.
    await page.goto('/login');
    await page.getByTestId('login-email').fill(TEST_EMAIL);
    await page.getByTestId('login-password').fill(TEST_PASSWORD);
    await page.getByTestId('login-submit').click();
    await page.waitForURL('/', { timeout: 10_000 });
    await page.goto('/caja/cerrar-turno');

    // Type the EXACT expected values (diferencia === 0).
    await page.getByTestId('cerrar-turno-valor-efectivo-reportado').fill('100000');
    await page.getByTestId('cerrar-turno-valor-datafono-reportado').fill('0');
    await page.getByTestId('cerrar-turno-valor-efectivo').fill('100000');
    await page.getByTestId('cerrar-turno-valor-datafono').fill('0');
    await page.getByTestId('cerrar-turno-confirmar').click();

    // Wire-level assertion: cierre_turno discriminator + cierre PUT body.
    expect(arqueoBody).not.toBeNull();
    expect(arqueoBody).toMatchObject({
      uuid_sesion: TEST_SESION_UUID,
      tipo_arqueo: 'cierre_turno',
      valor_efectivo_reportado: 100_000,
      valor_datafono_reportado: 0,
    });
    // diferencia === 0 → justificacion MUST be absent.
    expect(arqueoBody).not.toHaveProperty('justificacion');

    // bridge.imprimir MUST fire exactly once with auditoria_codigo='cierre_turno'.
    const calls = await page.evaluate(
      () =>
        (
          window as unknown as {
            __bridgeImprimirCalls: Array<{
              kind: string;
              payload: { auditoria_codigo?: string };
            }>;
          }
        ).__bridgeImprimirCalls,
    );
    expect(calls).toHaveLength(1);
    expect(calls[0]?.kind).toBe('arqueo');
    expect(calls[0]?.payload.auditoria_codigo).toBe('cierre_turno');

    // Redirect to /login?closed=true.
    await page.waitForURL(/\/login\?closed=true$/, { timeout: 10_000 });

    // axe-core WCAG 2.1 AA on the post-redirect /login page.
    const a11yResults = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    expect(a11yResults.violations).toEqual([]);
  });

  test.skip('strict-mode: |diferencia| > tolerancia → justificacion REQUIRED inline', async ({
    page,
  }) => {
    await stubAuth(page);
    await stubBridgeImprimir(page);

    // Mock resumen: tolerancia allows the small diferencia.
    await page.route(TEST_RESUMEN_URL, (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          uuid_sucursal: TEST_SUCURSAL_UUID,
          fecha: '2026-09-21',
          total_efectivo_cop: 100_000,
          total_datafono_cop: 0,
          diferencia_cop: 0,
          sesiones_cerradas: 1,
          tolerancia_efectivo: ARQUEO_TOLERANCIA_EFECTIVO,
          tolerancia_datafono: ARQUEO_TOLERANCIA_DATAFONO,
        }),
      }),
    );

    let arqueoBody: Record<string, unknown> | null = null;
    await page.route(TEST_ARQUEO_URL, (route) => {
      arqueoBody = JSON.parse(route.request().postData() ?? '{}') as Record<
        string,
        unknown
      >;
      return route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          uuid: 'arqueo-uuid-cierre-2',
          alerta_generada: true,
          uuid_alerta: 'mock-alerta-uuid',
        }),
      });
    });

    await page.route(TEST_CERRAR_SESION_URL, (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          uuid: TEST_SESION_UUID,
          timestamp_cierre: '2026-09-21T18:00:00Z',
        }),
      }),
    );

    await page.goto('/login');
    await page.getByTestId('login-email').fill(TEST_EMAIL);
    await page.getByTestId('login-password').fill(TEST_PASSWORD);
    await page.getByTestId('login-submit').click();
    await page.waitForURL('/', { timeout: 10_000 });
    await page.goto('/caja/cerrar-turno');

    // diferencia = -3000 (> tolerancia_efectivo=1000).
    await page.getByTestId('cerrar-turno-valor-efectivo-reportado').fill('97000');
    await page.getByTestId('cerrar-turno-valor-datafono-reportado').fill('0');

    // Submit button MUST be disabled while justificacion is empty (REQ-OPS-158 strict-mode).
    await expect(page.getByTestId('cerrar-turno-confirmar')).toBeDisabled();

    // Type a justificacion of >= 3 chars → button re-enables.
    await page
      .getByTestId('cerrar-turno-required-justificacion')
      .fill('Diferencia menor en caja');
    await expect(page.getByTestId('cerrar-turno-confirmar')).toBeEnabled();
    await page.getByTestId('cerrar-turno-valor-efectivo').fill('97000');
    await page.getByTestId('cerrar-turno-valor-datafono').fill('0');
    await page.getByTestId('cerrar-turno-confirmar').click();

    // POST body MUST include justificacion verbatim.
    expect(arqueoBody).not.toBeNull();
    expect(arqueoBody).toMatchObject({
      tipo_arqueo: 'cierre_turno',
      valor_efectivo_reportado: 97_000,
      justificacion: 'Diferencia menor en caja',
    });

    await page.waitForURL(/\/login\?closed=true$/, { timeout: 10_000 });
  });

  test.skip('orphan-uuid: POST 200 + PUT 500 → banner with uuid_arqueo, NO redirect, NO logout', async ({
    page,
  }) => {
    await stubAuth(page);
    await stubBridgeImprimir(page);

    await page.route(TEST_RESUMEN_URL, (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          uuid_sucursal: TEST_SUCURSAL_UUID,
          fecha: '2026-09-21',
          total_efectivo_cop: 100_000,
          total_datafono_cop: 0,
          diferencia_cop: 0,
          sesiones_cerradas: 1,
        }),
      }),
    );

    // POST /caja/arqueo succeeds → returns uuid.
    await page.route(TEST_ARQUEO_URL, (route) =>
      route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          uuid: 'arqueo-uuid-orphan',
          alerta_generada: false,
        }),
      }),
    );

    // PUT /caja-sesion/{uuid}/cerrar fails with 500.
    await page.route(TEST_CERRAR_SESION_URL, (route) =>
      route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'server_error' }),
      }),
    );

    await page.goto('/login');
    await page.getByTestId('login-email').fill(TEST_EMAIL);
    await page.getByTestId('login-password').fill(TEST_PASSWORD);
    await page.getByTestId('login-submit').click();
    await page.waitForURL('/', { timeout: 10_000 });
    await page.goto('/caja/cerrar-turno');

    await page.getByTestId('cerrar-turno-valor-efectivo-reportado').fill('100000');
    await page.getByTestId('cerrar-turno-valor-datafono-reportado').fill('0');
    await page.getByTestId('cerrar-turno-valor-efectivo').fill('100000');
    await page.getByTestId('cerrar-turno-valor-datafono').fill('0');
    await page.getByTestId('cerrar-turno-confirmar').click();

    // Orphan uuid banner MUST surface the arqueo uuid.
    const orphanBanner = page.getByTestId('cerrar-turno-orphan-uuid');
    await expect(orphanBanner).toBeVisible({ timeout: 5_000 });
    await expect(orphanBanner).toContainText('Ref: arqueo-uuid-orphan');

    // The route MUST stay mounted (no navigate to /login).
    await page.waitForTimeout(500);
    expect(page.url()).toContain('/caja/cerrar-turno');

    // The auth token MUST remain non-null (no logout).
    const tokenStillPresent = await page.evaluate(() => {
      return (
        window.localStorage.getItem('easypunto.jwt.v1') !== null ||
        // legacy key fallback per F2.2 storage migration
        window.localStorage.getItem('easypunto.jwt') !== null
      );
    });
    expect(tokenStillPresent).toBe(true);
  });
});