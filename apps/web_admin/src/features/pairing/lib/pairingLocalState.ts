/**
 * `pairingLocalState.ts` — localStorage-backed workaround for BR4 of
 * HU-F19.3.
 *
 * The real-world gap: `GET /api/v1/sucursales` declares a
 * `last_pairing_at` field but the backend hardcodes it to `null` (not
 * wired yet), and there is no "list pairing tokens by uuid_sucursal"
 * endpoint. A sucursal's pairing status therefore cannot be derived
 * from any backend call alone — this module is the documented
 * workaround: remember, per browser, the last pairing-token uuid this
 * admin issued for each sucursal, so `<Pairing />` can look its status
 * up one-by-one via `GET /admin/pairing-tokens/{uuid}`.
 *
 * This is a KNOWN, INTENTIONAL limitation: a token issued from a
 * different browser/session is invisible here. `<Pairing />` surfaces
 * an explanatory caption for this; this module just owns the storage.
 *
 * All localStorage access is guarded against throwing (private
 * browsing / SSR / quota-exceeded) — failures no-op rather than crash
 * the page.
 */

const STORAGE_KEY = 'easypunto.pairing.lastToken.v1';

interface PairingLocalRecord {
  pairingTokenUuid: string;
  issuedAt: string;
}

type PairingLocalMap = Record<string, PairingLocalRecord>;

function readMap(): PairingLocalMap {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== 'object' || parsed === null) return {};
    return parsed as PairingLocalMap;
  } catch {
    return {};
  }
}

function writeMap(map: PairingLocalMap): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(map));
  } catch {
    // Private browsing / quota exceeded / no localStorage -- no-op.
  }
}

/** Returns the last-known pairing-token uuid issued for this sucursal from this browser, or `null`. */
export function getLastTokenUuid(sucursalUuid: string): string | null {
  const map = readMap();
  return map[sucursalUuid]?.pairingTokenUuid ?? null;
}

/** Records the pairing-token uuid just issued for this sucursal, from this browser. */
export function setLastTokenUuid(sucursalUuid: string, pairingTokenUuid: string): void {
  const map = readMap();
  map[sucursalUuid] = { pairingTokenUuid, issuedAt: new Date().toISOString() };
  writeMap(map);
}
