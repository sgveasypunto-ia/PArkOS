"""catalog/local_only_catalog.py — LOCAL_ONLY_CATALOG (T-PR2-014, D6-rev).

Exactly 3 entries (REQ-CAT-003): ``idempotency_keys``, ``pairing_tokens``,
``revoked_sync_jwts`` — non-ER operational tables, never replicated, never
enqueued into ``sync_queue``.

``factura_electronica`` and ``revocacion_factura`` do **not** appear here
(superseded by D6-rev — see ``entries/sync_entries_le.py`` and
``entries/sync_entries_a.py``, which hold their single ``SYNC_CATALOG``
entries).

``direction=None`` on all three entries: REQ-CAT-001 states ``direction`` is
``None`` iff ``sync_strategy="never_propagated"``, but these three carry
``sync_strategy="local_only"`` instead and are never replicated in any
direction, so no ``Direction`` literal fits. ``schema.py``'s
``__post_init__`` relaxes the ``None`` guard for ``local_only`` alongside
``never_propagated`` for this reason — a real interpretation gap in
REQ-CAT-001's literal text, flagged rather than resolved by inventing a
placeholder direction value. See the PR2 apply report's "Deviations"
section.
"""
from __future__ import annotations

from ...models.A.idempotency_keys import IdempotencyKeys
from ...models.A.pairing_tokens import PairingToken
from ...models.A.revoked_sync_jwts import RevokedSyncJwt
from .schema import SyncCatalogEntry

_IDEMPOTENCY_KEYS = SyncCatalogEntry(
    name="idempotency_keys",
    model_cls=IdempotencyKeys,
    audit_class="A",
    sync_strategy="local_only",
    direction=None,
    broadcast_policy=None,
    apply_strategy=None,
    role_required="both",
    depends_on=(),
    has_uuid_sucursal=False,
    seq_strategy="none",
)

_PAIRING_TOKENS = SyncCatalogEntry(
    name="pairing_tokens",
    model_cls=PairingToken,
    audit_class="A",
    sync_strategy="local_only",
    direction=None,
    broadcast_policy=None,
    apply_strategy=None,
    role_required="both",
    depends_on=(),
    has_uuid_sucursal=False,
    seq_strategy="none",
)

_REVOKED_SYNC_JWTS = SyncCatalogEntry(
    name="revoked_sync_jwts",
    model_cls=RevokedSyncJwt,
    audit_class="A",
    sync_strategy="local_only",
    direction=None,
    broadcast_policy=None,
    apply_strategy=None,
    role_required="both",
    depends_on=(),
    has_uuid_sucursal=False,
    seq_strategy="none",
)

LOCAL_ONLY_CATALOG: tuple[SyncCatalogEntry, ...] = (
    _IDEMPOTENCY_KEYS,
    _PAIRING_TOKENS,
    _REVOKED_SYNC_JWTS,
)

assert len(LOCAL_ONLY_CATALOG) == 3, f"expected 3 LocalOnlyCatalog entries, got {len(LOCAL_ONLY_CATALOG)}"

__all__ = ["LOCAL_ONLY_CATALOG"]
