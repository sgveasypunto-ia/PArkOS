"""dian/cloud/sweep.py - find branch invoices the cloud never forwarded (DD1).

The branch emits ``factura_electronica`` and replicates it (its local
``pendiente`` ``envio_dian`` marker is NOT pushed: ``envio_dian`` is
cloud-authored). The cloud forwards to the provider asynchronously from a
post-commit hook; if that one-shot dispatch never ran (process restarted
between commit and task, source row not yet visible, unreadable token, ...)
nothing ever resumed the document and it stayed without any cloud chain
forever.

This module only SELECTS candidates. Dispatching is done by the caller through
the normal deferred path (``dispatch_*_with_backoff(skip_if_dispatched=True)``),
whose advisory lock + chain check guarantees a document is never submitted to
the provider twice, and whose backoff schedule is the rate limit.

A document is a candidate when ALL hold:
  * the cloud's ``factura_electronica`` row was received more than
    ``older_than`` ago;
  * it has NO cloud-originated chain (any ``envio_dian`` with
    ``payload.xml_sha256``) - an existing chain owns the document, finished
    (``aceptado`` / exhausted ``error`` + alert) or not;
  * fewer than ``max_failures`` ``dian_error`` alertas reference it (a
    document whose dispatch keeps dying before an envio exists needs a human,
    not an endless loop).

A cloud chain interrupted while a row was IN FLIGHT (its dispatcher died
before appending an outcome) is found by :func:`find_stale_inflight`.

Known gap (documented, not handled): a cloud chain whose last row is a
non-accepted TERMINAL one and was interrupted mid-backoff by a process restart
is not resumed, because the chain's sleeps (up to 24 h) cannot be told apart
from a dead task without a heartbeat column.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from ...models.L_E.factura_electronica import FacturaElectronica
from ...models.L_W.alerta import Alerta
from ...models.L_W.envio_dian import EnvioDian

DEFAULT_STALE_AFTER = timedelta(minutes=10)
DEFAULT_MAX_FAILURES = 5
DEFAULT_BATCH = 5
# A single dispatch attempt (send + poll windows) finishes in ~25 min at most;
# the long outer backoff sleeps happen AFTER a terminal row is appended, so an
# in-flight row older than this has lost its dispatcher.
DEFAULT_INFLIGHT_STALE_AFTER = timedelta(hours=1)
DEFAULT_MAX_INTERRUPTIONS = 3
_EN_CURSO = ("activo", "enviado", "en_proceso")


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
            chain.c.uuid_factura_electronica == FacturaElectronica.uuid,
            chain.c.payload["xml_sha256"].astext.is_not(None),
        )
        .exists()
    )
    failures = (
        select(func.count())
        .select_from(Alerta)
        .where(
            Alerta.tipo_alerta == "dian_error",
            Alerta.uuid_arqueo == FacturaElectronica.uuid,
        )
        .scalar_subquery()
    )
    stmt = (
        select(FacturaElectronica.uuid)
        .where(
            FacturaElectronica.created_at < cutoff,
            ~has_cloud_chain,
            failures < max_failures,
        )
        .order_by(FacturaElectronica.created_at)
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


async def find_stale_inflight(
    session: AsyncSession,
    *,
    older_than: timedelta = DEFAULT_INFLIGHT_STALE_AFTER,
    max_interruptions: int = DEFAULT_MAX_INTERRUPTIONS,
    limit: int = DEFAULT_BATCH,
    now: datetime | None = None,
) -> list[uuid_lib.UUID]:
    """``factura_electronica`` uuids whose cloud chain is stuck IN FLIGHT.

    ``envio_dian`` is append-only: the state of a chain is its LAST row. A chain
    whose last row is still ``activo`` / ``enviado`` / ``en_proceso`` and older
    than ``older_than`` has no live dispatcher (a live one appends its outcome
    within minutes). The dispatch guard (advisory lock + chain check, see
    ``dispatch_factura_electronica(recover_orphans_after=...)``) closes the
    orphan with an ``error`` row and, only when the provider never received the
    document (``activo``), sends it once more; a document recovered
    ``max_interruptions`` times needs a human and is no longer selected.
    """
    cutoff = (now or datetime.now(UTC).replace(tzinfo=None)) - older_than
    later = aliased(EnvioDian)
    interrupted = aliased(EnvioDian)
    superseded = (
        select(later.uuid)
        .where(
            later.uuid_factura_electronica == EnvioDian.uuid_factura_electronica,
            later.payload["xml_sha256"].astext.is_not(None),
            later.payload["uuid_revocacion_factura"].astext.is_(None),
            or_(
                later.timestamp_evento > EnvioDian.timestamp_evento,
                and_(
                    later.timestamp_evento == EnvioDian.timestamp_evento,
                    later.uuid > EnvioDian.uuid,
                ),
            ),
        )
        .exists()
    )
    interruptions = (
        select(func.count())
        .select_from(interrupted)
        .where(
            interrupted.uuid_factura_electronica == EnvioDian.uuid_factura_electronica,
            interrupted.payload["interrupted"].astext == "true",
        )
        .scalar_subquery()
    )
    stmt = (
        select(EnvioDian.uuid_factura_electronica)
        .where(
            EnvioDian.estado.in_(_EN_CURSO),
            EnvioDian.uuid_factura_electronica.is_not(None),
            EnvioDian.payload["xml_sha256"].astext.is_not(None),
            EnvioDian.payload["uuid_revocacion_factura"].astext.is_(None),
            EnvioDian.timestamp_evento < cutoff,
            ~superseded,
            interruptions < max_interruptions,
        )
        .group_by(EnvioDian.uuid_factura_electronica)
        .order_by(func.min(EnvioDian.timestamp_evento))
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())
