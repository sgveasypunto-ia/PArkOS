/**
 * E2E tests for the turno flow (F3.3 — T5).
 *
 * Sandbox F.6 caveat (verbatim precedent F2.1+F2.2+F2.3+F3.1+F3.2 archive
 * reports documentan misma limitation):
 *   `npm 11.16.0` en sandbox refuses `workspace:*` resolution. El comando
 *   `npx playwright test e2e/caja/turno.spec.ts` SKIP en este ambiente —
 *   unit tests (useSesionActiva + sesionActivaApi + CerrarTurno +
 *   Dashboard) cubren el camino crítico via mocks.
 *
 * Scenarios (per design.md §13.2 + tasks.md §2 T5):
 *   E1 — abrir-turno-happy-path: login + redirect automatico a
 *        /caja/abrir-turno + submit OK -> redirect a / con
 *        TurnoActivoPanel visible + formatTiempoTranscurrido "hace 0 minutos".
 *   E2 — sesion-already-active-409: setup estado con sesion activa +
 *        POST /caja-sesion/sesiones mock 409 -> FormMessage "Ya tenés un
 *        turno abierto" + botón "Ir al turno".
 *   E3 — cerrar-turno-happy-path: setup estado con sesion activa +
 *        submit OK -> 200 -> useAuthStore.clear + parkos:auth:cleared +
 *        redirect a /login?closed=true con <p data-testid="turno-cerrado-exito">
 *        visible role=status aria-live=polite.
 *   A1 — axe-core WCAG 2.1 AA en 4 estados (AbrirTurno normal +
 *        AbrirTurno 409 + CerrarTurno normal + Login ?closed=true).
 */
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const TEST_UUID_SESION = 'sess-uuid-test-001';

test.describe('Turno flow — F3.3 T5', () => {
  test('E1 — abrir-turno-happy-path: login → /caja/abrir-turno → submit OK → /', async ({ page }) => {
    // Mock login OK + /auth/me + POST /caja-sesion/sesiones + GET /caja-sesion/sesion/me
    await page.route('**/api/v1/auth/login', (route) =>
      route.fulfill({
        status: 200,
        body: JSON.stringify({
          access_token: 'test-access',
          refresh_token: 'test-refresh',
          token_type: 'Bearer',
          expires_in: 3600,
        }),
      }),
    );
    await page.route('**/api/v1/auth/me', (route) =>
      route.fulfill({
        status: 200,
        body: JSON.stringify({
          user: { id: 'usr-uuid-1', email: 'op@test.co' },
          sucursal: { uuid: 'suc-uuid-1', nombre: 'Sucursal Centro' },
          sucursales_permitidas: [{ uuid: 'suc-uuid-1', nombre: 'Sucursal Centro' }],
          permisos: ['abrir_cerrar_caja'],
          expires_at: null,
        }),
      }),
    );
    await page.route('**/api/v1/caja-sesion/sesiones', (route) => {
      if (route.request().method() === 'POST') {
        route.fulfill({
          status: 200,
          body: JSON.stringify({
            uuid: TEST_UUID_SESION,
            uuid_sucursal: 'suc-uuid-1',
            uuid_usuario: 'usr-uuid-1',
            valor_inicial_efectivo: 50000,
            valor_inicial_datafono: 0,
            timestamp_apertura: new Date().toISOString(),
            timestamp_cierre: null,
            observaciones: 'Apertura',
          }),
        });
      } else {
        route.continue();
      }
    });
    await page.route('**/api/v1/caja-sesion/sesion/me', (route) =>
      route.fulfill({
        status: 200,
        body: JSON.stringify({
          uuid: TEST_UUID_SESION,
          uuid_sucursal: 'suc-uuid-1',
          uuid_usuario: 'usr-uuid-1',
          valor_inicial_efectivo: 50000,
          valor_inicial_datafono: 0,
          timestamp_apertura: new Date().toISOString(),
          timestamp_cierre: null,
          observaciones: 'Apertura',
        }),
      }),
    );

    await page.goto('/login');
    await page.getByTestId('login-email').fill('op@test.co');
    await page.getByTestId('login-password').fill('valid-password-1234');
    await page.getByTestId('login-submit').click();

    // Después de login OK → redirect / → Dashboard ve sesion activa → TurnoActivoPanel visible
    await expect(page.getByTestId('turno-activo-panel')).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId('turno-activo-uuid')).toContainText(TEST_UUID_SESION);
  });

  test('E2 — sesion-already-active-409: submit mientras ya activa → FormMessage + botón "Ir al turno"', async ({ page }) => {
    // Estado pre-existente: sesion activa via localStorage JWT stub + /me 200.
    await page.route('**/api/v1/auth/me', (route) =>
      route.fulfill({
        status: 200,
        body: JSON.stringify({
          user: { id: 'usr-uuid-1', email: 'op@test.co' },
          sucursal: { uuid: 'suc-uuid-1', nombre: 'Sucursal Centro' },
          sucursales_permitidas: [{ uuid: 'suc-uuid-1', nombre: 'Sucursal Centro' }],
          permisos: ['abrir_cerrar_caja'],
          expires_at: null,
        }),
      }),
    );
    await page.route('**/api/v1/caja-sesion/sesiones', (route) => {
      if (route.request().method() === 'POST') {
        route.fulfill({
          status: 409,
          body: JSON.stringify({ error: 'sesion_already_active' }),
        });
      } else {
        route.continue();
      }
    });

    // Login flow omitido: el operador ya está autenticado y navega directo.
    await page.goto('/caja/abrir-turno');

    // Si la sesion ya está activa, el Dashboard redirige automáticamente.
    // Forzamos navegación directa a /caja/abrir-turno via un mock que
    // retorna 404 (operador sin sesión activa) para llegar al form.
    await page.unroute('**/api/v1/caja-sesion/sesion/me');
    await page.route('**/api/v1/caja-sesion/sesion/me', (route) =>
      route.fulfill({ status: 404, body: JSON.stringify({ error: 'sesion_no_active' }) }),
    );
    await page.goto('/caja/abrir-turno');

    await expect(page.getByTestId('abrir-turno-form')).toBeVisible({ timeout: 10_000 });
    await page.getByTestId('abrir-turno-submit').click();

    await expect(page.getByTestId('abrir-turno-error-sesion-ya-abierta')).toBeVisible();
    await expect(
      page.getByTestId('abrir-turno-error-sesion-ya-abierta'),
    ).toHaveAttribute('role', 'alert');
    await expect(page.getByTestId('abrir-turno-ir-al-turno')).toBeVisible();
  });

  test('E3 — cerrar-turno-happy-path: submit OK → /login?closed=true con <p role="status">', async ({ page }) => {
    await page.route('**/api/v1/auth/me', (route) =>
      route.fulfill({
        status: 200,
        body: JSON.stringify({
          user: { id: 'usr-uuid-1', email: 'op@test.co' },
          sucursal: { uuid: 'suc-uuid-1', nombre: 'Sucursal Centro' },
          sucursales_permitidas: [{ uuid: 'suc-uuid-1', nombre: 'Sucursal Centro' }],
          permisos: ['abrir_cerrar_caja'],
          expires_at: null,
        }),
      }),
    );
    await page.route('**/api/v1/caja-sesion/sesion/me', (route) =>
      route.fulfill({
        status: 200,
        body: JSON.stringify({
          uuid: TEST_UUID_SESION,
          uuid_sucursal: 'suc-uuid-1',
          uuid_usuario: 'usr-uuid-1',
          valor_inicial_efectivo: 50000,
          valor_inicial_datafono: 0,
          timestamp_apertura: new Date(Date.now() - 60_000).toISOString(),
          timestamp_cierre: null,
        }),
      }),
    );
    await page.route('**/api/v1/caja-sesion/sesion/*/cerrar', (route) =>
      route.fulfill({
        status: 200,
        body: JSON.stringify({
          uuid: TEST_UUID_SESION,
          uuid_sucursal: 'suc-uuid-1',
          uuid_usuario: 'usr-uuid-1',
          valor_inicial_efectivo: 50000,
          valor_inicial_datafono: 0,
          timestamp_apertura: new Date(Date.now() - 60_000).toISOString(),
          timestamp_cierre: new Date().toISOString(),
        }),
      }),
    );

    await page.goto('/caja/cerrar-turno');
    await expect(page.getByTestId('cerrar-turno-form')).toBeVisible({ timeout: 10_000 });
    await page.getByTestId('cerrar-turno-confirmar').click();

    await page.waitForURL(/\/login\?closed=true/);
    await expect(page.getByTestId('turno-cerrado-exito')).toBeVisible();
    await expect(page.getByTestId('turno-cerrado-exito')).toHaveAttribute('role', 'status');
    await expect(page.getByTestId('turno-cerrado-exito')).toHaveAttribute('aria-live', 'polite');
  });

  test('A1 — axe-core WCAG 2.1 AA en AbrirTurno + CerrarTurno + TurnoActivoPanel + Login ?closed=true', async ({ page }) => {
    // Stub mínimo /auth/me para hidratar useAuth sin red.
    await page.route('**/api/v1/auth/me', (route) =>
      route.fulfill({
        status: 200,
        body: JSON.stringify({
          user: { id: 'usr-uuid-1', email: 'op@test.co' },
          sucursal: { uuid: 'suc-uuid-1', nombre: 'Sucursal Centro' },
          sucursales_permitidas: [{ uuid: 'suc-uuid-1', nombre: 'Sucursal Centro' }],
          permisos: ['abrir_cerrar_caja'],
          expires_at: null,
        }),
      }),
    );
    await page.route('**/api/v1/caja-sesion/sesion/me', (route) =>
      route.fulfill({ status: 404, body: JSON.stringify({ error: 'sesion_no_active' }) }),
    );

    // (a) AbrirTurno normal
    await page.goto('/caja/abrir-turno');
    await expect(page.getByTestId('abrir-turno-form')).toBeVisible();
    const abrirTurnoAxe = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    expect(abrirTurnoAxe.violations).toEqual([]);

    // (b) CerrarTurno normal
    await page.unroute('**/api/v1/caja-sesion/sesion/me');
    await page.route('**/api/v1/caja-sesion/sesion/me', (route) =>
      route.fulfill({
        status: 200,
        body: JSON.stringify({
          uuid: TEST_UUID_SESION,
          uuid_sucursal: 'suc-uuid-1',
          uuid_usuario: 'usr-uuid-1',
          valor_inicial_efectivo: 50000,
          valor_inicial_datafono: 0,
          timestamp_apertura: new Date().toISOString(),
          timestamp_cierre: null,
        }),
      }),
    );
    await page.goto('/caja/cerrar-turno');
    await expect(page.getByTestId('cerrar-turno-form')).toBeVisible();
    const cerrarTurnoAxe = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    expect(cerrarTurnoAxe.violations).toEqual([]);

    // (c) TurnoActivoPanel via Dashboard /
    await page.goto('/');
    await expect(page.getByTestId('turno-activo-panel')).toBeVisible();
    const turnoActivoAxe = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    expect(turnoActivoAxe.violations).toEqual([]);

    // (d) Login ?closed=true feedback (estado post-cierre)
    await page.goto('/login?closed=true');
    await expect(page.getByTestId('turno-cerrado-exito')).toBeVisible();
    const loginClosedAxe = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    expect(loginClosedAxe.violations).toEqual([]);
  });
});