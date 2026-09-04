# web_admin

Multi-tenant admin PWA for **Parkos** — the cloud-side surface that
operators use to manage branches, configuration, and DIAN invoice flow.

This is the **bootstrap** PWA shell (PR10b). The BranchSelector, admin
`/me` wiring, and full dashboard come in PR10c.

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

- PR10c — BranchSelector + `/admin/me` wiring (T-PR10-10..T-PR10-13)
- PR11d — DIAN invoice preview surfaces (reuses the Button + Card primitives)
- PR12  — web_sucursal (sibling workspace)
