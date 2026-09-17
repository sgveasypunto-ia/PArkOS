/**
 * `useDashboardDrawerStore` — Zustand singleton for the operator
 * dashboard's single-drawer invariant (REQ-OPS-138, REQ-OPS-136).
 *
 * The dashboard composes six feature panels + one singleton drawer
 * slot. Only ONE drawer may be visible at a time; opening a new
 * drawer MUST close the previous one. `Esc` / close MUST restore DOM
 * focus to the trigger that opened the active drawer.
 *
 * The store is intentionally minimal:
 *   - `openDrawer` — the currently visible drawer kind, or `null`.
 *   - `lastAnchorId` — the `id` of the trigger element that opened the
 *     drawer; consumed by the close-handler to restore focus.
 *   - `initialPlaca` — the optional plate typed into the dashboard
 *     hero input that triggered the drawer (entry point for the
 *     "smart routing" flow in F6/F7). Read by `<IngresoSheet />` and
 *     `<SalidaSheet />` to pre-fill their respective forms on mount.
 *   - `open(kind, anchorId, placa?)` — sets `openDrawer = kind`,
 *     remembers the anchor, and optionally records the triggering
 *     placa. The placa arg is optional and defaults to `null` so
 *     existing callers (sidebar buttons, hotkeys) stay backward-
 *     compatible. Calling `open(...)` while a drawer is already open
 *     is a clean swap: only the latest drawer becomes visible.
 *   - `close()` — clears `openDrawer`, `lastAnchorId`, and `initialPlaca`.
 *     The component owning the active drawer is responsible for
 *     invoking `document.getElementById(lastAnchorId)?.focus()` in its
 *     close-effect (REQ-OPS-138 §Esc).
 *
 * Per plan.md §0.2 the dashboard drawer state is "estado de UI local
 * efímero" — Zustand is the canonical surface for ephemeral UI state
 * in this codebase (precedent: `useAuthStore` at `@parkos/ui-kit/store`).
 */
import { create } from 'zustand';

export type DrawerKind =
  | 'pago'
  | 'fe-retry'
  | 'reimpresion'
  | 'arqueo'
  | 'cierre-diario'
  | 'ingreso'
  | 'salida'
  | 'suscripciones'
  | 'inventario'
  | null;

export type NonNullDrawerKind = Exclude<DrawerKind, null>;

export interface DashboardDrawerState {
  openDrawer: DrawerKind;
  lastAnchorId: string | null;
  /**
   * Plate typed into the dashboard `PlacaInputHero` that triggered the
   * currently-open drawer. Consumed by `<IngresoSheet />` and
   * `<SalidaSheet />` to pre-fill their forms on mount (F6.1/F7.1
   * smart routing). `null` for hotkey/sidebar-driven opens.
   */
  initialPlaca: string | null;
  /**
   * Open a drawer. The optional `placa` arg records the plate that
   * triggered the open so the drawer can pre-fill its form; it is
   * ignored by drawers that don't need it.
   */
  open(kind: NonNullDrawerKind, anchorId: string, placa?: string | null): void;
  close(): void;
}

export const useDashboardDrawerStore = create<DashboardDrawerState>((set) => ({
  openDrawer: null,
  lastAnchorId: null,
  initialPlaca: null,
  open: (kind, anchorId, placa = null) =>
    set({ openDrawer: kind, lastAnchorId: anchorId, initialPlaca: placa }),
  close: () =>
    set({ openDrawer: null, lastAnchorId: null, initialPlaca: null }),
}));

/**
 * Convenience guard: returns `true` when the supplied kind is the
 * currently-open drawer. Used by Sheet/Dialog `open` props so that
 * the active drawer stays mounted only when its kind matches.
 */
export function isDrawerOpen(
  state: Pick<DashboardDrawerState, 'openDrawer'>,
  kind: NonNullDrawerKind,
): boolean {
  return state.openDrawer === kind;
}
