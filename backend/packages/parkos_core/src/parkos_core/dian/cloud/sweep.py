"""dian/cloud/sweep.py - find branch invoices the cloud never forwarded (DD1).

The branch emits ``factura_electronica`` plus a ``pendiente`` ``envio_dian``
and replicates both. The cloud forwards to the provider asynchronously from a
post-commit hook; if that one-shot dispatch never ran (process restarted
between commit and task, source row not yet visible, unreadable token, ...)
nothing ever resumed the document and its ``envio_dian`` stayed ``pendiente``
forever.

This module only SELECTS candidates. Dispatching is done by the caller through
the normal deferred path (``dispatch_*_with_backoff(skip_if_dispatched=True)``),
whose advisory lock + chain check guarantees a document is never submitted to
the provider twice, and whose backoff schedule is the rate limit.

A document is a candidate when ALL hold:
  * it has a branch-originated ``envio_dian`` in ``estado='pendiente'`` (no
    ``payload.xml_sha256``: that key is written only by the cloud dispatcher)
    older than ``older_than``;
  * it has NO cloud-originated chain (any ``envio_dian`` with
    ``payload.xml_sha256``) - an existing chain owns the document, finished
    (``aceptado`` / exhausted ``error`` + alert) or not;
  * fewer than ``max_failures`` ``dian_error`` alertas reference it (a
    document whose dispatch keeps dying before an envio exists needs a human,
    not an endless loop).

Known gap (documented, not handled): a cloud chain interrupted mid-backoff by
a process restart is not resumed, because the chain's sleeps (up to 24 h)
cannot be told apart from a dead task without a heartbeat column.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.L_W.alerta import Alerta
from ...models.L_W.envio_dian import EnvioDian

DEFAULT_STALE_AFTER = timedelta(minutes=10)
DEFAULT_MAX_FAILURES = 5
DEFAULT_BATCH = 5


async def find_stale_pendientes(
    session: AsyncSession,
    *,
    older_than: timedelta = DEFAULT_STALE_AFTER,
    max_failures: int = DEFAULT_MAX_FAILURES,
    limit: int = DEFAULT_BATCH,
    now: datetime | None = None,
) -> list[uuid_lib.UUID]:
    """Return the ``factura_electronica`` uuids to resume, oldest first."""
    cutoff = (now or datetime.now(UTC).replace(tzinfo=None)) - older_than

    chain = EnvioDian.__table__.alias("chain")
    has_cloud_chain = (
        select(chain.c.uuid)
        .where(
            chain.c.uuid_factura_electronica == EnvioDian.uuid_factura_electronica,
            chain.c.payload["xml_sha256"].astext.is_not(None),
        )
        .exists()
    )
    failures = (
        select(func.count())
        .select_from(Alerta)
        .where(
            Alerta.tipo_alerta == "dian_error",
            Alerta.uuid_arqueo == EnvioDian.uuid_factura_electronica,
        )
        .scalar_subquery()
    )
    stmt = (
        select(EnvioDian.uuid_factura_electronica)
        .where(
            EnvioDian.estado == "pendiente",
            EnvioDian.uuid_factura_electronica.is_not(None),
            EnvioDian.payload["xml_sha256"].astext.is_(None),
            EnvioDian.payload["uuid_revocacion_factura"].astext.is_(None),
            EnvioDian.created_at < cutoff,
            ~has_cloud_chain,
            failures < max_failures,
        )
        .group_by(EnvioDian.uuid_factura_electronica)
        .order_by(func.min(EnvioDian.created_at))
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())
