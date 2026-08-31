# PWA Scaffolds Specification

## Purpose

Defines the React 18 + Vite 5 + TypeScript-strict scaffolds for `apps/web_admin`, `apps/web_sucursal`, and the shared `apps/ui-kit`. Establishes the toolchain, the offline-first shell shipped in this bootstrap (auth + health + placeholder routes), the multi-branch vs branch-pinned UX distinction, and the WCAG enforcement gate.

## Requirements

### Requirement: Standardized PWA Toolchain

Every PWA workspace MUST use React 18, Vite 5, TypeScript strict, `shadcn/ui` as the only UI library, `zustand` for global state, `react-hook-form` + `zod` for forms, `i18next` with `es-CO` default, `vite-plugin-pwa`, `idb`, and `@axe-core/playwright` wired into CI. The `tsconfig` MUST enable `strict`, `noUncheckedIndexedAccess`, and `exactOptionalPropertyTypes`.

#### Scenario: Both apps declare the same stack

- GIVEN `apps/web_admin/package.json` and `apps/web_sucursal/package.json`
- WHEN inspected
- THEN both list `react@^18`, `vite@^5`, `typescript@^5`, `zustand`, `react-hook-form`, `zod`, `i18next`, `vite-plugin-pwa`, `idb`
- AND both include `@axe-core/playwright` in `devDependencies`.

#### Scenario: TypeScript strict gate

- GIVEN the strict `tsconfig.json`
- WHEN CI runs `tsc --noEmit`
- THEN any implicit `any`, unhandled index access, or non-optional `undefined` field fails the build.

### Requirement: Shared UI Kit as Workspace Package

`apps/ui-kit/` MUST export the `cn()` helper, shadcn-generated components (Button, Card, Input, Form, Dialog, Toast), CSS-variable design tokens (`src/styles/tokens.css`), and shared Zod schemas. `web_admin` and `web_sucursal` MUST depend on `ui-kit` via `"ui-kit": "workspace:*"`.

#### Scenario: Design tokens override white-label per tenant

- GIVEN the host page sets `<html class="tenant-3">`
- WHEN the CSS variables for `tenant-3` load
- THEN `bg-primary` and `text-foreground` reflect tenant-3's values across both PWAs.

### Requirement: Offline Shell Only at Bootstrap

Each PWA MUST ship only the offline shell: a service worker that caches the app shell, an `auth` screen, a `/health` route, and placeholder routes. PWAs MUST NOT contain CRUD screens, business logic, or sync worker code.

#### Scenario: Service worker caches the shell on first visit

- GIVEN a fresh operator visit with no network
- WHEN they reopen the PWA after the first online visit
- THEN `vite-plugin-pwa`'s precache list serves `/`, `/health`, and the auth screen from cache.

#### Scenario: Offline IndexedDB queue stub exists

- GIVEN the operator triggers an offline placeholder action
- WHEN the app calls `db.sync_queue.put(...)`
- THEN the call succeeds (the table exists), but no real sync worker drains it yet.

### Requirement: Multi-Branch UX for `web_admin`

`web_admin` MUST render a branch selector listing every UUID in the JWT's `sucursales_permitidas` claim. Each API call MUST include the chosen UUID in `X-Sucursal-Context`. Default selection MUST be the first permitted branch.

#### Scenario: Selector renders from JWT

- GIVEN the admin's JWT carries `sucursales_permitidas: ["<A>", "<B>"]`
- WHEN the operator opens `web_admin`
- THEN the selector shows `<A>` and `<B>` and defaults to `<A>`.

#### Scenario: Switching branches updates the header

- GIVEN the operator picks `<B>`
- WHEN the next API call fires
- THEN the request includes `X-Sucursal-Context: <B>`
- AND the API returns branch-B data.

### Requirement: Branch-Pinned UX for `web_sucursal`

`web_sucursal` MUST NOT show a branch selector; the JWT carries a single `sucursal_id`. The tenancy middleware MUST reject cross-branch requests with `403`.

#### Scenario: No branch selector exists

- GIVEN `web_sucursal/src/`
- WHEN the operator loads the app
- THEN no branch selector renders
- AND the JWT's `sucursal_id` is the only branch.

#### Scenario: Cross-branch request is rejected

- GIVEN the operator's JWT carries `sucursal_id: <A>`
- WHEN a request is issued with `X-Sucursal-Context: <B>`
- THEN the API returns HTTP `403`.

### Requirement: WCAG 2.1 AA CI Gate

CI MUST run `@axe-core/playwright` against a smoke test of each PWA and MUST fail the build on any AA violation. The gate MUST be a required check on PRs that touch `apps/`.

#### Scenario: A11y violations block merge

- GIVEN a new component introduces an unlabeled button
- WHEN CI runs `axe-core` against the affected page
- THEN the check exits non-zero
- AND the PR cannot merge.