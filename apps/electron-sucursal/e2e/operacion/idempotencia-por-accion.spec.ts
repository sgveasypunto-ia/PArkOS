/**
 * `idempotencia-por-accion.spec.ts` — Idempotency-Key per USER ACTION.
 *
 * Contract under test (`withActionIdempotencyKey` + `parkosFetch`):
 *   (a) a double click on the SAME visible action (two identical calls that
 *       overlap in flight) shares ONE key, so the backend dedupes them;
 *   (b) two SEPARATE user actions with identical bodies (exit -> annul ->
 *       exit, or exit -> re-entry of the same plate) get DIFFERENT keys, so
 *       the backend never replays an old result for a new action;
 *   (c) a transport / 5xx retry of the SAME attempt re-uses its key.
 *
 * The real modules are loaded from the Vite dev server inside a plain
 * Chromium page (no Electron, no backend): `page.route()` plays the backend,
 * including `Idempotency-Key` replay, which is what made the old content-hash
 * keys dangerous.
 *
 * Run: start the sucursal renderer detached (see
 * `.claude/skills/run-electron-sucursal/SKILL.md`) and
 *   PARKOS_E2E_WEB_URL=http://127.0.0.1:5173 npx playwright test e2e/operacion/idempotencia-por-accion.spec.ts
 * `PARKOS_E2E_CHROME_PATH` optionally points at a local Chrome/Chromium.
 */
import { test, expect, chromium, type Browser, type Page } from '@playwright/test';

const BASE_URL = process.env.PARKOS_E2E_WEB_URL ?? 'http://127.0.0.1:5173';
const INGRESOS = '**/api/v1/operacion/ingresos';
const SALIDAS = '**/api/v1/operacion/salidas';
const HEX64 = /^[0-9a-f]{64}$/;

interface Seen {
  key: string;
  body: string;
}

let browser: Browser;
let page: Page;

test.beforeAll(async () => {
  browser = await chromium.launch({
    executablePath: process.env.PARKOS_E2E_CHROME_PATH || undefined,
  });
});

test.afterAll(async () => {
  await browser.close();
});

test.beforeEach(async () => {
  page = await browser.newPage();
  const res = await page.goto(BASE_URL, { waitUntil: 'domcontentloaded' });
  const title = await page.title();
  test.skip(
    res === null || !/Parkos Sucursal/i.test(title),
    `${BASE_URL} does not serve the sucursal renderer (title="${title}")`,
  );
});

test.afterEach(async () => {
  await page.close();
});

/**
 * Backend emulation with `IdempotencyKeyMiddleware` semantics: the first
 * response stored for a key is replayed for every later request with that
 * key. Records every request seen.
 */
async function mockIdempotentBackend(
  p: Page,
  glob: string,
  opts: { delayMs?: number; failFirstWith?: number } = {},
): Promise<{ seen: Seen[]; rows: () => number }> {
  const seen: Seen[] = [];
  const stored = new Map<string, string>();
  let created = 0;
  let failed = false;
  await p.route(glob, async (route) => {
    const req = route.request();
    const key = req.headers()['idempotency-key'] ?? '';
    seen.push({ key, body: req.postData() ?? '' });
    if (opts.delayMs) await new Promise((r) => setTimeout(r, opts.delayMs));
    if (opts.failFirstWith && !failed) {
      failed = true;
      await route.fulfill({ status: opts.failFirstWith, body: 'busy' });
      return;
    }
    let payload = stored.get(key);
    if (payload === undefined) {
      created += 1;
      const uuid = `00000000-0000-4000-8000-${String(created).padStart(12, '0')}`;
      payload = JSON.stringify({
        uuid,
        tipo_entrada: 'ROTACION',
        uuid_subscripcion_cliente: null,
        consecutivo: null,
      });
      stored.set(key, payload);
    }
    await route.fulfill({
      status: 201,
      contentType: 'application/json',
      body: payload,
    });
  });
  return { seen, rows: () => created };
}

const PLACA = { placa_presente: true, placa: 'ABC123' } as const;

/** Runs the REAL `postIngreso` (withActionIdempotencyKey + parkosFetch). */
async function postIngresoN(p: Page, mode: 'concurrent' | 'sequential', n: number) {
  return p.evaluate(
    async ({ payload, mode: m, count }) => {
      const mod = (await import(
        /* @vite-ignore */ '/src/features/operacion/lib/ingresoApi.ts'
      )) as { postIngreso: (b: unknown) => Promise<{ uuid: string }> };
      const calls = Array.from({ length: count }, () => () => mod.postIngreso(payload));
      if (m === 'concurrent') return Promise.all(calls.map((c) => c()));
      const out: { uuid: string }[] = [];
      for (const c of calls) out.push(await c());
      return out;
    },
    { payload: PLACA, mode, count: n },
  );
}

test.describe('Idempotency-Key por acción de usuario', () => {
  test('(a) doble clic (llamadas idénticas en vuelo) comparten UNA llave y crean una sola fila', async () => {
    const backend = await mockIdempotentBackend(page, INGRESOS, { delayMs: 150 });
    const results = await postIngresoN(page, 'concurrent', 2);

    expect(backend.seen).toHaveLength(2);
    expect(backend.seen[0]!.key).toMatch(HEX64);
    expect(backend.seen[1]!.key).toBe(backend.seen[0]!.key);
    expect(backend.rows()).toBe(1);
    expect(results[1]!.uuid).toBe(results[0]!.uuid);
  });

  test('(b) ingreso -> salida -> reingreso de la misma placa envía llaves DISTINTAS y crea otra fila', async () => {
    const backend = await mockIdempotentBackend(page, INGRESOS);
    const results = await postIngresoN(page, 'sequential', 2);

    expect(backend.seen).toHaveLength(2);
    expect(backend.seen[0]!.body).toBe(backend.seen[1]!.body);
    expect(backend.seen[0]!.key).toMatch(HEX64);
    expect(backend.seen[1]!.key).toMatch(HEX64);
    expect(backend.seen[1]!.key).not.toBe(backend.seen[0]!.key);
    // The old content-hash key made the backend replay the FIRST ingreso.
    expect(backend.rows()).toBe(2);
    expect(results[1]!.uuid).not.toBe(results[0]!.uuid);
  });

  test('(b) salida -> anular -> salida (mismo body, acciones separadas) usa llaves DISTINTAS', async () => {
    const backend = await mockIdempotentBackend(page, SALIDAS);
    await page.evaluate(async () => {
      const { withActionIdempotencyKey } = (await import(
        /* @vite-ignore */ '/src/features/operacion/lib/idempotency.ts'
      )) as typeof import('../../src/features/operacion/lib/idempotency');
      const { parkosFetch } = (await import(
        /* @vite-ignore */ '/@id/@parkos/ui-kit/fetch'
      )) as { parkosFetch: (p: string, i: unknown) => Promise<unknown> };
      const path = '/api/v1/operacion/salidas';
      const body = { uuid_ingreso: '00000000-0000-4000-8000-0000000000aa' };
      const exit = () =>
        withActionIdempotencyKey({ method: 'POST', path, body }, (key) =>
          parkosFetch(path, {
            method: 'POST',
            body: JSON.stringify(body),
            headers: { 'Idempotency-Key': key },
          }),
        );
      await exit(); // 1st exit
      // (operator dismisses the payment drawer = "anular" -> action settled)
      await exit(); // 2nd exit of the same ingreso
    });

    expect(backend.seen).toHaveLength(2);
    expect(backend.seen[1]!.key).not.toBe(backend.seen[0]!.key);
    expect(backend.rows()).toBe(2);
  });

  test('(b) un reintento deliberado tras un fallo visible usa una llave NUEVA', async () => {
    // 4xx is a definitive answer (no transport retry): the operator clicks again.
    const seen: string[] = [];
    await page.route(INGRESOS, (route) => {
      seen.push(route.request().headers()['idempotency-key'] ?? '');
      void route.fulfill({ status: 422, contentType: 'application/json', body: '{"detail":"x"}' });
    });
    await page.evaluate(async (payload) => {
      const mod = (await import(
        /* @vite-ignore */ '/src/features/operacion/lib/ingresoApi.ts'
      )) as { postIngreso: (b: unknown) => Promise<unknown> };
      for (let i = 0; i < 2; i += 1) {
        await mod.postIngreso(payload).catch(() => undefined);
      }
    }, PLACA);

    expect(seen).toHaveLength(2);
    expect(seen[0]).toMatch(HEX64);
    expect(seen[1]).not.toBe(seen[0]);
  });

  test('(c) reintento de transporte (503 y luego 201) de la MISMA acción reutiliza la llave', async () => {
    const backend = await mockIdempotentBackend(page, INGRESOS, { failFirstWith: 503 });
    const results = await postIngresoN(page, 'sequential', 1);

    expect(backend.seen).toHaveLength(2); // 503 + retry
    expect(backend.seen[0]!.key).toMatch(HEX64);
    expect(backend.seen[1]!.key).toBe(backend.seen[0]!.key);
    expect(backend.rows()).toBe(1);
    expect(results[0]!.uuid).toBeTruthy();

    // ...and the NEXT user action gets a different key.
    await postIngresoN(page, 'sequential', 1);
    expect(backend.seen).toHaveLength(3);
    expect(backend.seen[2]!.key).not.toBe(backend.seen[0]!.key);
  });

  test('parkosFetch sin llave del llamador: dos POST idénticos separados -> llaves distintas; reintento 5xx -> misma llave', async () => {
    const keys: string[] = [];
    let first = true;
    await page.route('**/api/e2e/idem', (route) => {
      keys.push(route.request().headers()['idempotency-key'] ?? '');
      if (first && keys.length === 3) {
        first = false;
        void route.fulfill({ status: 503, body: 'busy' });
        return;
      }
      void route.fulfill({ status: 201, contentType: 'application/json', body: '{}' });
    });
    await page.evaluate(async () => {
      const { parkosFetch } = (await import(
        /* @vite-ignore */ '/@id/@parkos/ui-kit/fetch'
      )) as { parkosFetch: (p: string, i: unknown) => Promise<unknown> };
      const init = { method: 'POST', body: JSON.stringify({ a: 1 }) };
      await parkosFetch('/api/e2e/idem', init);
      await parkosFetch('/api/e2e/idem', init);
      await parkosFetch('/api/e2e/idem', init); // 503 -> internal retry
    });

    expect(keys).toHaveLength(4);
    expect(keys[0]).toMatch(HEX64);
    expect(keys[1]).not.toBe(keys[0]);
    expect(keys[3]).toBe(keys[2]);
    expect(keys[2]).not.toBe(keys[1]);
  });
});
