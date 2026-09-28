# web_admin

Multi-tenant admin PWA for **Parkos** — the cloud-side surface that
operators use to manage branches, configuration, and DIAN invoice flow.

This is the **cloud-admin PWA**. After login the admin lands on
`/seleccionar-sucursal` (gate), picks a branch, and works inside
`/dashboard` with tabs that scope the configuration surfaces to the
active branch.

## Stack

- **React 18 + TypeScript strict** (Vite 5)
- **Tailwind CSS** + **shadcn/ui** design tokens (CSS variables)
- **Zustand** for app state, **react-hook-form** + **Zod** for forms
- **i18next** (`es-CO` default per project canon)
- **React Router 6** for routing
- **vite-plugin-pwa** for the offline shell (manifest + service worker)
- **@axe-core/playwright** for WCAG 2.1 AA CI gate
- **vitest** + **@testing-library/react** for unit tests
- **Playwright** for end-to-end tests

## Scripts

| Command | What it does |
| --- | --- |
| `npm run dev` | Vite dev server with HMR (port `5173`) |
| `npm run build` | `tsc -b` + Vite production build |
| `npm run preview` | Preview the production build on port `5173` |
| `npm run lint` | ESLint with `--max-warnings 0` |
| `npm run test` | vitest (single run, jsdom env) |
| `npm run test:e2e` | Playwright (boots `npm run dev` first, then runs `e2e/`) |

> Run from the **repo root** with `npm --workspace=web_admin run <script>`,
> or from this directory directly. The repo root's `apps/package.json`
> orchestrates the full frontend suite via `npm-run-all`.

## Layout

```
apps/web_admin/
├── public/                    # static assets (manifest.json, icons)
├── src/
│   ├── components/ui/         # shadcn-generated UI primitives
│   ├── i18n/                  # i18next + locales
│   ├── lib/                   # cn() helper + future services
│   ├── pages/                 # route components (Login, Dashboard, ...)
│   ├── App.tsx                # router
│   ├── main.tsx               # entry
│   ├── index.css              # Tailwind + shadcn CSS variables
│   └── test-setup.ts          # @testing-library/jest-dom matchers
├── e2e/                       # Playwright specs
├── components.json            # shadcn config
├── index.html                 # Vite entry
├── playwright.config.ts
├── tailwind.config.ts
├── tsconfig*.json
└── vite.config.ts
```

## Adding shadcn components

```bash
cd apps/web_admin
npx shadcn@latest add dialog dropdown-menu form input select sheet table textarea tabs toast tooltip
```

Each component lands under `src/components/ui/`. **Do not edit those
files manually** — wrap them if you need custom behavior (see
`react` + `shadcn` skills).

## WCAG 2.1 AA

The Playwright config's `e2e/smoke.spec.ts` runs `@axe-core/playwright`
with tags `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa` against `/dashboard`.
Any violation fails CI. RNF-022 is the source-of-truth requirement.

## Where to go next

- PR1 (`feat(web_admin): gate de sucursal + selector global en topbar`) — landed on `dev`.
- PR2 (`feat(web_admin): tab 'Mi sucursal activa' en features de configuracion`) — landed on `dev`.
- PR3 (`feat(web_admin): gestion de usuarios (lista + asignar sucursales)`) — landed on `dev`.

## Dev: clearing a stale Service Worker

`vite dev` does **not** register a Service Worker — only the
production build does (via `vite-plugin-pwa` + `registerSW.js`).
If you previously ran `npm run preview` or served the `dist/` folder
on port `5173` and then switched back to `vite dev`, the old SW
stays registered in the browser and serves the pre-PR bundle from
its precache. Symptoms: `Ctrl+R` shows old UI, `Ctrl+F5` (hard
reload) shows new UI.

Fix once after the first merge that changes the shell:

1. F12 → Application → Service Workers → **Unregister** the entry for `127.0.0.1:5173`.
2. If the Unregister button is missing, F12 → Application → Storage → **Clear site data**.
3. Reload with `Ctrl+R`.

After that one-time clear, `vite dev` serves the live code without
interception. The build-side SW (`registerType: 'autoUpdate'` in
`vite.config.ts`) only kicks in on `npm run preview` or in
containerized deployments where `dist/` is served by nginx.
