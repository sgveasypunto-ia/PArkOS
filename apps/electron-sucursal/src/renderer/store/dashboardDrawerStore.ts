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
 *   - `pagoContext` — F8.1 (HU-F8.1 — PagoModal). The
 *     `{uuid_ingreso, total_cop}` pair that `<SalidaPanel>` pushes
 *     when opening the `pago` drawer. Read by `<DrawerHost />` and
 *     forwarded to `<PagoSheet />` so the form can build the
 *     `POST /facturacion/factura` body without re-fetching the
 *     cotizacion.
 *   - `open(kind, anchorId, placa?, pagoContext?)` — sets
 *     `openDrawer = kind`, remembers the anchor, optionally records
 *     the triggering placa, and optionally pushes the pago context.
 *     The placa and pagoContext args are optional and default to
 *     `null` so existing callers (sidebar buttons, hotkeys) stay
 *     backward-compatible. Calling `open(...)` while a drawer is
 *     already open is a clean swap: only the latest drawer becomes
 *     visible.
 *   - `close()` — clears `openDrawer`, `lastAnchorId`, `initialPlaca`,
 *     and `pagoContext`. The component owning the active drawer is
 *     responsible for invoking
 *     `document.getElementById(lastAnchorId)?.focus()` in its
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
  | 'cerrar-turno'
  | 'cierre-diario'
  | 'ingreso'
  | 'salida'
  | 'suscripciones'
  | 'inventario'
  | null;

export type NonNullDrawerKind = Exclude<DrawerKind, null>;

/**
 * F8.1 (HU-F8.1 — PagoModal) — context payload that travels with
 * the `pago` drawer open. The renderer's `<SalidaPanel>` knows the
 * `uuid_ingreso` (Path 1 result from `useIngresoActivo`) and the
 * cotizacion's `total_cents` at the moment the operator clicks
 * "Cobrar" — passing both via the drawer context avoids a redundant
 * fetch inside `<PagoSheet>` and guarantees the form starts with the
 * SAME values the operator just approved.
 *
 * F8.1-b (HU-F8.1-anular-salida-no-pagada, 2026-09-23) — also carries
 * `uuid_salida` so `<PagoSheet>` can auto-annul the salida on any
 * close-without-pay path (Cancelar button / X / overlay click /
 * Escape). Without this, the ingreso would stay closed (the salida
 * row already inserted by `POST /operacion/salidas` would lock
 * `V_INGRESO_ESTADO` to `cerrado`) and the operator could never
 * recover the cobro. The annulation is a workflow `[L-W]` row in
 * `prod.anulaciones` (already supported by the BE — `tipo_anulable`
 * polymorphic with `salida` arm).
 */
export interface PagoContext {
  uuid_ingreso: string;
  uuid_salida: string;
  /** Pre-IVA base (`cotizacion.subtotal`) — stored on `prod.facturas.subtotal`. */
  subtotal_cop: number;
  total_cop: number;
}

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
   * F8.1 — pago drawer context. `null` when a non-pago drawer is
   * active (or when no drawer is open). Set by `<SalidaPanel>::handleOpenPago`
   * before `open('pago', ...)`, read by `<DrawerHost>` to forward
   * `<PagoSheet>` the live `uuid_ingreso` + `total_cop` from the
   * cotizacion snapshot the operator just approved.
   */
  pagoContext: PagoContext | null;
  /**
   * Open a drawer. The optional `placa` arg records the plate that
   * triggered the open so the drawer can pre-fill its form; it is
   * ignored by drawers that don't need it. The optional `pagoContext`
   * arg records the `uuid_ingreso` + `total_cop` for the `pago`
   * drawer.
   */
  open(
    kind: NonNullDrawerKind,
    anchorId: string,
    placa?: string | null,
    pagoContext?: PagoContext | null,
  ): void;
  close(): void;
}

export const useDashboardDrawerStore = create<DashboardDrawerState>((set) => ({
  openDrawer: null,
  lastAnchorId: null,
  initialPlaca: null,
  pagoContext: null,
  open: (kind, anchorId, placa = null, pagoContext = null) =>
    set({
      openDrawer: kind,
      lastAnchorId: anchorId,
      initialPlaca: placa,
      pagoContext: pagoContext,
    }),
  close: () =>
    set({
      openDrawer: null,
      lastAnchorId: null,
      initialPlaca: null,
      pagoContext: null,
    }),
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