"""DIAN HTTP dispatcher (T-PR11-01 + T-PR11-07).

Serializes a ``factura_electronica`` row to UBL 2.1, sends it to the
DIAN provider (Factus by default), and records the outcome as an
``envio_dian`` row.

Target state machine per design §21.11:

1. Serialize the row via :func:`ubl_serializer.serialize`.
2. ``POST {PARKOS_DIAN_PROVIDER_URL}/api/ubl2.1`` via
   :class:`FactusProvider`.
3. Poll ``GET /api/ubl2.1/{trackId}`` every 2s up to
   ``PARKOS_DIAN_TIMEOUT_S``.
4. On ``aceptado``: ``envio_dian.estado='aceptado'`` + ``cufe``.
5. On ``rechazado``: ``envio_dian.estado='rechazado'`` + ``alerta``.
6. On timeout: ``schedule_retry`` with ``backoff_5xx`` (1m, 5m, 15m).

**Scope of this PR**: steps 1-3 (serialize + send) plus the initial
``envio_dian`` record. Steps 3-6 (the poll loop, the rejection/timeout
branches, the ``alerta`` chain roots, and ``dispatch_revocacion``
T-PR11-02) land in the follow-up PR together with the mock-transport
test suite (T-PR11-08 through T-PR11-10).

Issuer: cloud-only (module-level import guard below).
"""
from __future__ import annotations

import hashlib
import os
import uuid as uuid_lib
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Module-level import guard (T-PR11-07 — DIAN boundary layer 2).
# MUST stay the first non-stdlib statement so branch deploys bail out at
# module load, before the DIAN ORM models are ever imported.
if os.environ.get("PARKOS_DEPLOY", "cloud").lower() == "branch":
    raise ImportError(
        "dian_cloud_unavailable_on_branch (T-PR11-07, REQ-X3, design §10 Layer 2)"
    )

from ...models.L_E.factura_electronica import FacturaElectronica
from ...models.L_W.envio_dian import EnvioDian
from .dian_providers.factus import DianProvider, FactusProvider, PollResult
from .ubl_serializer import serialize


async def dispatch_factura_electronica(
    session: AsyncSession,
    *,
    uuid_factura_electronica: uuid_lib.UUID,
    actor_uuid: uuid_lib.UUID,
    dian_provider_url: str,
    dian_token_path: Path,
) -> EnvioDian:
    """Send a ``factura_electronica`` to DIAN and record the ``envio_dian`` row.

    Args:
        session: Active ``AsyncSession``.
        uuid_factura_electronica: The row to dispatch.
        actor_uuid: JWT subject (the admin who triggered the dispatch).
        dian_provider_url: ``PARKOS_DIAN_PROVIDER_URL``.
        dian_token_path: ``PARKOS_DIAN_PROVIDER_TOKEN_PATH``.

    Returns:
        The newly inserted :class:`EnvioDian` row.

    Raises:
        RuntimeError: If the ``factura_electronica`` row is not found.
        httpx.HTTPStatusError: If the provider rejects the send. The
            follow-up PR converts this into an ``envio_dian`` row with
            ``estado='rechazado'`` plus an ``alerta`` chain root rather
            than letting it escape.
    """
    # 1. Load the row.
    row = (
        await session.execute(
            select(FacturaElectronica).where(
                FacturaElectronica.uuid == uuid_factura_electronica
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise RuntimeError(
            f"factura_electronica {uuid_factura_electronica} not found"
        )

    # 2. Serialize to UBL 2.1.
    xml_bytes = serialize(row)

    # 3. Send via the provider adapter.
    provider: DianProvider = FactusProvider(
        base_url=dian_provider_url,
        token_path=dian_token_path,
    )
    track_id = await provider.send_ubl(xml_bytes)

    # 4. Record the send. The poll loop that resolves this into
    #    'aceptado' / 'rechazado' / 'timeout' lands in the follow-up PR;
    #    ``estado`` is intentionally left to the column default so the
    #    row never claims a DIAN outcome we have not observed yet.
    #    The DB ``AFTER INSERT`` trigger on ``envio_dian`` enqueues the
    #    matching ``sync_queue`` row (PR2 §12).
    now = datetime.now(UTC).replace(tzinfo=None)
    envio = EnvioDian(
        uuid_sucursal=row.uuid_sucursal,
        uuid_factura_electronica=row.uuid,
        uuid_resolucion_facturacion=row.uuid_resolucion_facturacion,
        payload={
            "track_id": track_id,
            "xml_sha256": hashlib.sha256(xml_bytes).hexdigest(),
        },
        uuid_envio_padre=None,
        timestamp_evento=now,
        created_at=now,
        created_by=actor_uuid,
    )
    session.add(envio)
    await session.commit()
    await session.refresh(envio)
    return envio


__all__ = [
    "DianProvider",
    "FactusProvider",
    "PollResult",
    "dispatch_factura_electronica",
]
