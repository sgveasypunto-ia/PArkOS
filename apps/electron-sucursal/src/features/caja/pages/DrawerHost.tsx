/**
 * `<DrawerHost />` — singleton drawer slot driven by
 * `useDashboardDrawerStore` (REQ-OPS-138).
 *
 * Renders ONE drawer at a time, gated by `openDrawer === <kind>`. Each
 * future PR adds its own drawer kind + mount branch (PagoSheet in PR-3,
 * ReimprimirTiqueteSheet in PR-4, ArqueoSheet + CierreDiarioDialog in
 * PR-5). For PR-1 the host is intentionally empty — no drawer is
 * available yet, but the infrastructure is in place to add kinds.
 *
 * Focus restoration per REQ-OPS-138 §Esc: when a drawer closes, the
 * `useDashboardDrawerStore` consumer restores DOM focus to the
 * `data-anchor-for="<kind>"` element. Each drawer branch in this
 * component is responsible for its own focus-restore in its
 * `onOpenChange(false)` effect; this host is the structural seam.
 */
import { useDashboardDrawerStore } from '@/store/dashboardDrawerStore';

/**
 * PR-1 placeholder: no drawer is wired yet. Future PRs add branches
 * here (`if (openDrawer === 'pago') ...`).
 *
 * Returns `JSX.Element | null` to satisfy strict React 18 typing —
 * returning `null` from a React component is the idiomatic "render
 * nothing" signal.
 */
export function DrawerHost(): JSX.Element | null {
  const openDrawer = useDashboardDrawerStore((s) => s.openDrawer);

  // No drawer is wired in PR-1 — the host exists so future PRs can
  // add branches by adding `if (openDrawer === 'pago')` etc.
  if (!openDrawer) return null;
  return null;
}