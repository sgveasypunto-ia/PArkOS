# Pruebas E2E + Chrome DevTools — easypunto_parkos

> **Pruebas E2E automatizadas con Chrome DevTools Protocol (CDP)** vía Playwright.
> Aplica a **apps/electron-sucursal** (`_electron.launch`) y **apps/web_admin** (chromium headless).
> Última ejecución verificada: **2026-09-17**.

Playwright usa CDP internamente — cada `page.context().newCDPSession(page)` expone la API completa de Chrome DevTools (Network, Performance, DOM, Console, etc.) para automation reproducible.

---

## 0. Resumen rápido (TL;DR)

| Suite E2E | Comando (raíz) | Tiempo | Estado sandbox |
|---|---|---|---|
| electron-sucursal (scaffold + WCAG) | `cd apps/electron-sucursal && npm run test:e2e` | ~3 min | ⏭️ SKIP-env (requiere Electron built `out/main.js`) |
| electron-sucursal (kiosko) | `npm run test:e2e -- kiosko.spec.ts` | ~2 min | ⏭️ SKIP-env |
| electron-sucursal (lifecycle) | `npm run test:e2e -- lifecycle.spec.ts` | ~2 min | ⏭️ SKIP-env |
| electron-sucursal (printer) | `npm run test:e2e -- printer.spec.ts` | ~2 min | ⏭️ SKIP-env |
| web_admin (smoke + WCAG) | `cd apps/web_admin && npm run test:e2e` | ~3 min | ⏭️ SKIP-env (requiere `npm run dev` o build) |
| web_admin (branch-selector) | `npm run test:e2e -- branch-selector.spec.ts` | ~1 min | ⏭️ SKIP-env |
| **CDP performance profiling** | script custom con `chrome-remote-interface` o Playwright `cdp` | TBD | nuevo |
| **CDP coverage report** | script custom Playwright `page.coverage` | TBD | nuevo |
| **CDP network HAR capture** | `await page.routeFromHAR(...)` o custom | TBD | nuevo |

**Regla universal**: `npm run test:e2e` requiere la app construida (`npm run build` primero). En sandbox sin Electron built = SKIP-env. CI matrix de GitHub Actions lo cubre en runner con Electron prebuilt.

---

## 1. Infra existente

### 1.1 electron-sucursal — `playwright.config.ts`

```typescript
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  timeout: 60_000,
});
```

Levanta Electron vía `_electron.launch({ args: ['.'] })` (usa `out/main.js` empaquetado). Captura **trace on first retry** + **screenshot on failure** automáticamente.

### 1.2 web_admin — `playwright.config.ts`

```typescript
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: {
    command: 'npm run dev',  // boot Vite dev server antes de tests
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    stdout: 'pipe',
  },
});
```

Levanta chromium headless + `npm run dev` automáticamente.

### 1.3 E2E specs existentes

| App | Archivo | Cubre |
|---|---|---|
| electron-sucursal | `e2e/scaffold.spec.ts` | app launches, renders Parkos Sucursal, axe-core WCAG 2.1 AA zero violations |
| electron-sucursal | `e2e/kiosko.spec.ts` | kiosko mode toggle + PIN unlock flow |
| electron-sucursal | `e2e/lifecycle.spec.ts` | app lifecycle (single-instance, quit) |
| electron-sucursal | `e2e/printer.spec.ts` | print:queue IPC handler smoke |
| web_admin | `e2e/smoke.spec.ts` | login redirect, branch selector render |
| web_admin | `e2e/branch-selector.spec.ts` | multi-branch dropdown + selection |

---

## 2. Comandos reproducibles

### 2.1 electron-sucursal — E2E completo

```powershell
cd E:\easypunto_parkos\apps\electron-sucursal

# 1. Build primero (requerido por Playwright electron launcher)
npm run build:main
npm run build:renderer

# 2. Correr E2E suite
npm run test:e2e

# 3. Correr spec individual
npm run test:e2e -- scaffold.spec.ts
npm run test:e2e -- kiosko.spec.ts

# 4. Modo interactivo (debug visual)
npm run test:e2e -- --headed

# 5. Con UI de Playwright (trace viewer)
npx playwright show-report
```

### 2.2 web_admin — E2E completo

```powershell
cd E:\easypunto_parkos\apps\web_admin

# 1. NO requiere build (Playwright arranca `npm run dev` automáticamente)
# 2. Correr E2E suite (boota Vite + corre chromium headless)
npm run test:e2e

# 3. Modo headed (con ventana visible)
npm run test:e2e -- --headed
```

### 2.3 Salidas generadas automáticamente

| Output | Path | Cuándo se genera |
|---|---|---|
| Trace viewer | `test-results/<spec>/trace.zip` | On first retry |
| Screenshots | `test-results/<spec>/test-failed-*.png` | On failure |
| HTML report | `playwright-report/index.html` | Después de cada run (CI mode) |
| Console logs | `test-results/<spec>/console.log` (con `outputDir`) | Si se configura |

---

## 3. Chrome DevTools Protocol (CDP) — automation extendida

Playwright expone CDP nativo. Para automation con DevTools API (Network, Performance, DOM, etc.):

### 3.1 Performance profiling (CDP `Performance` domain)

```typescript
import { test, expect, _electron as electron } from '@playwright/test';

test('measure FCP + LCP + TTFB on cold load', async () => {
  const app = await electron.launch({ args: ['.'] });
  const window = await app.firstWindow();
  const cdp = await window.context().newCDPSession(window);

  // Enable Performance domain
  await cdp.send('Performance.enable');

  const metrics: Record<string, number> = {};
  cdp.on('Performance.metrics', (event) => {
    for (const m of event.metrics) {
      metrics[m.name] = m.value;
    }
  });

  await window.reload();
  await window.waitForLoadState('load');

  // CDP metrics (timestamps in seconds since navigation start)
  console.log('FCP:', metrics['FirstContentfulPaint']);
  console.log('LCP:', metrics['LargestContentfulPaint']);
  console.log('TTFB:', metrics['TimeToFirstByte']);
  console.log('DomContentLoaded:', metrics['DomContentLoaded']);

  // Assertions
  expect(metrics['FirstContentfulPaint']).toBeLessThan(1500); // <1.5s
  expect(metrics['LargestContentfulPaint']).toBeLessThan(2500);

  await app.close();
});
```

### 3.2 Network HAR capture (CDP `Network` domain)

```typescript
import { test, _electron as electron } from '@playwright/test';
import * as fs from 'node:fs';

test('capture full network log as HAR file', async () => {
  const app = await electron.launch({ args: ['.'] });
  const window = await app.firstWindow();
  const cdp = await window.context().newCDPSession(window);

  const requests: unknown[] = [];
  cdp.on('Network.requestWillBeSent', (e) => requests.push(e));
  cdp.on('Network.responseReceived', (e) => requests.push(e));
  await cdp.send('Network.enable');

  // Trigger flow: login → abrir turno
  await window.getByRole('textbox', { name: /email/i }).fill('operador@example.com');
  // ... etc.

  fs.writeFileSync('network-trace.har', JSON.stringify(requests, null, 2));
  await app.close();
});
```

### 3.3 JS + CSS coverage report (CDP `Profiler` domain)

```typescript
import { test, expect, _electron as electron } from '@playwright/test';

test('measure JS coverage for / route', async () => {
  const app = await electron.launch({ args: ['.'] });
  const window = await app.firstWindow();
  const cdp = await window.context().newCDPSession(window);

  await cdp.send('Profiler.enable');
  await cdp.send('Profiler.startPreciseCoverage', {
    callCount: true,
    detailed: true,
  });

  await window.goto('/'); // navigate in electron
  await window.waitForLoadState('load');

  const result = await cdp.send('Profiler.takePreciseCoverage');
  let totalBytes = 0;
  let usedBytes = 0;
  for (const entry of result.result) {
    for (const func of entry.functions) {
      totalBytes += func.ranges.reduce((s, r) => s + (r.endOffset - r.startOffset), 0);
      usedBytes += func.ranges
        .filter((r) => r.count > 0)
        .reduce((s, r) => s + (r.endOffset - r.startOffset), 0);
    }
  }
  const coverage = (usedBytes / totalBytes) * 100;
  console.log(`JS coverage: ${coverage.toFixed(2)}%`);
  expect(coverage).toBeGreaterThan(40); // threshold

  await app.close();
});
```

### 3.4 Console + Network + Errors logging

```typescript
import { test, _electron as electron } from '@playwright/test';

test('capture all console messages and errors during flow', async () => {
  const app = await electron.launch({ args: ['.'] });
  const window = await app.firstWindow();

  const logs: string[] = [];
  window.on('console', (msg) => logs.push(`[${msg.type()}] ${msg.text()}`));
  window.on('pageerror', (err) => logs.push(`[PAGE_ERROR] ${err.message}`));

  // ... trigger flow ...

  // Assert no errors
  const errors = logs.filter((l) => l.startsWith('[error]') || l.startsWith('[PAGE_ERROR]'));
  expect(errors).toEqual([]);

  await app.close();
});
```

### 3.5 Video recording (CDP screencast)

```typescript
import { test, _electron as electron } from '@playwright/test';

test('record full operator flow as video', async () => {
  const app = await electron.launch({
    args: ['.'],
    // Habilita video recording por Playwright Electron
    recordVideo: { dir: 'e2e/videos/', size: { width: 1280, height: 800 } },
  });
  const window = await app.firstWindow();

  // ... full flow: login → abrir turno → 1 ingreso → 1 salida → cerrar turno ...

  // El video se guarda automáticamente al cerrar app
  await app.close();
  // → e2e/videos/<random-uuid>.webm
});
```

### 3.6 Lighthouse CI (CDP `Audits` domain)

```typescript
import { test, _electron as electron } from '@playwright/test';
import lighthouse from 'lighthouse';

test('lighthouse accessibility + performance audit', async () => {
  const app = await electron.launch({ args: ['.'] });
  const window = await app.firstWindow();
  const port = await app.evaluate(({ app: a }) => a.getAppPath());

  const result = await lighthouse('http://localhost:3000', {
    port, // CDP debugger port de Electron
    onlyCategories: ['accessibility', 'performance', 'best-practices'],
  });

  const scores = result.lhr.categories;
  expect(scores.accessibility.score).toBeGreaterThanOrEqual(0.95);
  expect(scores.performance.score).toBeGreaterThanOrEqual(0.8);
  await app.close();
});
```

---

## 4. Cómo agregar un nuevo E2E spec

### 4.1 Caso típico: flujo completo del operador (login → ingreso → salida)

```typescript
// apps/electron-sucursal/e2e/operador-flow.spec.ts
import { test, expect, _electron as electron } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test.describe('HU-F3.1/F6.1/F7.1/F7.2/F10.2 operator flow — full happy path', () => {
  let app: Awaited<ReturnType<typeof electron.launch>>;
  let window: Awaited<ReturnType<typeof app.firstWindow>>;

  test.beforeEach(async () => {
    app = await electron.launch({ args: ['.'] });
    window = await app.firstWindow();
    await window.waitForLoadState('domcontentloaded');
  });

  test.afterEach(async () => {
    await app.close();
  });

  test('F3.1 login → F3.3 abrir turno → F6.1 ingreso → F7.2 salida → F10.2 cerrar turno', async () => {
    // --- F3.1: login ---
    await window.getByLabel(/email/i).fill('operador@bog-cen.example');
    await window.getByLabel(/contraseña|password/i).fill('TestPass123!');
    await window.getByRole('button', { name: /ingresar|login/i }).click();
    await window.waitForURL(/\/$/);

    // --- F3.3: abrir turno ---
    await window.getByRole('button', { name: /abrir turno/i }).click();
    await window.getByLabel(/efectivo/i).fill('50000');
    await window.getByLabel(/datafono/i).fill('0');
    await window.getByRole('button', { name: /confirmar/i }).click();
    await expect(window.getByText(/turno activo/i)).toBeVisible();

    // --- F6.1: registrar ingreso ---
    await window.getByPlaceholder(/placa/i).fill('ABC123');
    await window.getByRole('button', { name: /registrar ingreso/i }).click();
    await expect(window.getByText(/ingreso registrado/i)).toBeVisible();

    // --- F7.2: registrar salida (después de >1 min o usar minutos negativos) ---
    await window.getByPlaceholder(/placa/i).fill('ABC123');
    await window.getByRole('button', { name: /registrar salida/i }).click();
    await window.getByLabel(/medio de pago/i).selectOption({ label: 'Efectivo' });
    await window.getByRole('button', { name: /cobrar|cobrar y salir/i }).click();
    await expect(window.getByText(/salida registrada/i)).toBeVisible();

    // --- F10.2: cerrar turno ---
    await window.getByRole('button', { name: /cerrar turno/i }).click();
    await expect(window.getByText(/turno cerrado/i)).toBeVisible();

    // --- WCAG 2.1 AA baseline (RNF-022) ---
    const a11yResults = await new AxeBuilder({ page: window })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    expect(a11yResults.violations).toEqual([]);
  });
});
```

### 4.2 Caso típico: smoke de web_admin (login multi-sucursal)

```typescript
// apps/web_admin/e2e/login-multi-branch.spec.ts
import { test, expect } from '@playwright/test';

test.describe('HU-F13.6 login + branch selector', () => {
  test('login redirige a branch-selector si multi-sucursal', async ({ page }) => {
    await page.goto('/login');
    await page.getByLabel(/email/i).fill('admin@example.com');
    await page.getByLabel(/contraseña|password/i).fill('AdminPass123!');
    await page.getByRole('button', { name: /ingresar/i }).click();
    await page.waitForURL(/\/branch-selector$/);
    await expect(page.getByRole('heading', { name: /seleccione sucursal/i })).toBeVisible();
  });

  test('selecciona "BOG-CEN" → dashboard', async ({ page }) => {
    // login + seleccionar branch
    // ...
    await page.getByRole('button', { name: /BOG-CEN/i }).click();
    await page.waitForURL(/\/dashboard$/);
    await expect(page.getByTestId('dashboard-hub')).toBeVisible();
  });
});
```

---

## 5. Chrome DevTools Protocol — domains disponibles

Playwright expone ~40 domains CDP. Los más útiles para automation:

| Domain | Para qué sirve |
|---|---|
| `Network` | Capturar requests/responses, throttle, interceptar, HAR export |
| `Performance` | Métricas (FCP, LCP, TTFB), traces |
| `Profiler` | JS + CSS coverage, sampling profiler |
| `Page` | Screenshots, screencast (video), print-to-PDF |
| `DOM` | Inspect DOM, getDocument, querySelectorAll |
| `CSS` | GetMatchedStylesForNode, force pseudo-states |
| `Runtime` | Evaluar JS expressions, getProperties |
| `Log` | Console messages (alternativa a `page.on('console')`) |
| `Tracing` | Performance trace (alternativa a Playwright trace) |
| `Audits` | Lighthouse audits |

Lista completa: https://chromedevtools.github.io/devtools-protocol/

---

## 6. CI/CD integration

### 6.1 GitHub Actions workflow (excerpt)

```yaml
# .github/workflows/e2e.yml
name: E2E + Chrome DevTools

on: [push, pull_request]

jobs:
  electron-sucursal-e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 20 }
      - run: cd apps && pnpm install --frozen-lockfile
      - run: cd apps/electron-sucursal && npm run build
      - run: cd apps/electron-sucursal && npm run test:e2e
      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: playwright-traces-electron
          path: apps/electron-sucursal/test-results/
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: lighthouse-reports
          path: apps/electron-sucursal/e2e/lighthouse/

  web_admin-e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 20 }
      - run: cd apps/web_admin && pnpm install --frozen-lockfile
      - run: cd apps/web_admin && npm run test:e2e
      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: playwright-traces-web-admin
          path: apps/web_admin/test-results/
```

### 6.2 Local pre-flight (antes de push)

```powershell
# electron-sucursal
cd E:\easypunto_parkos\apps\electron-sucursal
npm run build:main && npm run build:renderer
npm run test:e2e -- --reporter=list
# Si pasa: commit + push
# Si falla: npx playwright show-report y revisar test-results/
```

---

## 7. Troubleshooting

| Síntoma | Causa probable | Fix |
|---|---|---|
| `_electron.launch` falla con `Cannot find module out/main.js` | No se construyó | `npm run build:main && npm run build:renderer` |
| `webServer.url` timeout en web_admin | Vite no arranca | `npm run dev` manual para ver errores; chequear puerto 5173 |
| Tests flaky en kiosko | Timing-sensitive (PIN bcrypt ~250ms) | Aumentar `timeout` en playwright.config o usar `--retries 2` |
| `AxeBuilder` reporta violations pre-existing | UI no tiene a11y suficiente | Reportar como `KNOWN_VIOLATIONS` y excluirlos con `.exclude()` |
| Video recording no funciona | `recordVideo.dir` no writable | Verificar permisos de carpeta o usar `os.tmpdir()` |
| Trace viewer no abre | Falta `npx playwright show-report` o puerto ocupado | Cerrar instancias previas del trace viewer |

---

## 8. Orden de ejecución recomendado

### 8.1 Pre-flight rápido (CI matrix local)

```powershell
# 1. Backend unit (sin DB)
cd E:\easypunto_parkos\backend
uv run pytest tests/unit/ -q --tb=line

# 2. Frontend unit (sin browser)
cd E:\easypunto_parkos\apps\ui-kit
.\node_modules\.bin\vitest.CMD run

# 3. Frontend electron-sucursal unit
cd E:\easypunto_parkos\apps\electron-sucursal
.\node_modules\.bin\vitest.CMD run

# 4. (Si hay DB) Backend integration
cd E:\easypunto_parkos\backend
uv run pytest tests/integration/ -q --tb=line

# 5. (Si app built) E2E electron-sucursal
cd E:\easypunto_parkos\apps\electron-sucursal
npm run build && npm run test:e2e

# 6. (Requiere Node dev server) E2E web_admin
cd E:\easypunto_parkos\apps\web_admin
npm run test:e2e
```

Tiempo total sin DB + sin build: **~1 min**.
Tiempo total con DB + build: **~15 min**.

### 8.2 Modo debug (interactivo, solo dev local)

```powershell
# 1. Build electron-sucursal una vez
cd E:\easypunto_parkos\apps\electron-sucursal
npm run build

# 2. Lanzar electron manualmente (verás la ventana)
npm run dev

# 3. En otra terminal, lanzar Playwright con UI (headed)
npm run test:e2e -- --headed

# 4. Después del run, abrir trace viewer para cualquier test que falló
npx playwright show-report
```

---

## 9. Referencias

- `apps/electron-sucursal/playwright.config.ts` — config electron launcher
- `apps/web_admin/playwright.config.ts` — config PWA chromium
- `apps/electron-sucursal/e2e/` — specs existentes (scaffold, kiosko, lifecycle, printer)
- `apps/web_admin/e2e/` — specs existentes (smoke, branch-selector)
- `AGENTS.md` (raíz) — reglas operativas
- `pruebas.md` (raíz) — suite de tests unitarios backend + frontend
- Chrome DevTools Protocol domains: https://chromedevtools.github.io/devtools-protocol/
- Playwright Electron API: https://playwright.dev/docs/api/class-electron
- Playwright Trace Viewer: https://playwright.dev/docs/trace-viewer
- @axe-core/playwright: https://github.com/rapidezie/axe-core/tree/master/packages/playwright
