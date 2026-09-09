"""DIAN HTTP dispatcher — full state machine (T-PR11-01 + T-PR11-02, T-PR11-07).

Per design §21.11 / tasks.md T-PR11-01:
  1. Serialize ``factura_electronica`` via :func:`ubl_serializer.serialize`.
  2. ``POST`` to the DIAN provider (Factus).
  3. Poll ``GET /api/ubl2.1/{trackId}`` every 2s up to ``PARKOS_DIAN_TIMEOUT_S``.
  4. ``aceptado`` → write cufe + stamp DIAN 5-year retention.
  5. ``rechazado`` → capture motive + alerta chain root
     (``tipo_alerta='dian_rechazada'``).
  6. Timeout → retry up to ``PARKOS_DIAN_RETRY_MAX`` with
     ``backoff_5xx = (60s, 300s, 900s)`` between attempts.
  7. Final timeout → alerta chain root (``tipo_alerta='dian_timeout'``).

T-PR11-02 mirrors the same state machine for ``revocacion_factura``
(``POST /api/revocacion``); on ``aceptado`` it additionally extends
the SHA-256 chain on ``prod.revocacion_factura``. The branch learns the
DIAN ack arrived through the ORDINARY ``envio_dian`` ``cloud_to_branch``
catalog entry (``AFTER INSERT`` on ``envio_dian`` enqueues ``sync_queue``,
PR2 §12) — D1-rev (design.md §0 amendment #1) withdrew the outbound
placeholder this module used to enqueue here; see T-PR9-007/008.

T-PR9 additions (design.md §2 Issue #9, §7.3):
  8. Cloud-side range validation (:func:`validate_consecutivo_range`) runs
     BEFORE a ``factura_electronica`` is forwarded to the provider —
     rejects any document whose ``consecutivo`` falls outside its
     resolution's authorized range and raises ``alerta
     tipo_alerta='fe_numbering_exhausted'``.
  9. :func:`dispatch_factura_electronica_with_backoff` /
     :func:`dispatch_revocacion_with_backoff` drive the single-attempt
     dispatch functions below across up to ``DIAN_MAX_RETRIES`` (6)
     attempts, chained via ``uuid_envio_padre``, waiting
     ``DIAN_BACKOFF_SCHEDULE[attempt]`` between non-``aceptado``
     outcomes. Exhaustion stamps the terminal envio ``estado='error'`` /
     ``estado_dian='error'`` and raises ``alerta
     tipo_alerta='fe_provider_error'``. The single-attempt functions'
     OWN internal transport retry (``_send_initial``/``_poll_loop``,
     ``PARKOS_DIAN_RETRY_MAX``) is unchanged and runs INSIDE each
     attempt — the two retry layers are deliberately distinct (design.md
     §2 Issue #9: a per-attempt transport hiccup vs. the DIAN critical
     path's own 1m/5m/15m/1h/6h/24h escalation).

Known deviations from the design-as-written (model files immutable in
T-PR11-01):
  - ``envio_dian`` lacks a dedicated DIAN-outcome column; the outcome
    lives in ``respuesta_proveedor`` JSONB (``estado_dian``). ``estado``
    is declared elsewhere as the bi-temporal versioning flag
    (``WorkflowBase``) — this module (T-PR9-008/009) ALSO mirrors the
    SAME outcome value onto ``estado`` because
    ``prod.v_factura_electronica_acuse`` (migration 0009) projects
    ``estado`` directly for the branch to read. Root-insert writes
    (``parent_uuid=None``, as done here) never validate against
    ``repo.workflow.STATE_MACHINES`` — only a CHAINED transition does —
    so this dual use does not collide with that state machine's own
    ``pendiente``/``enviado``/``ack``/``error`` vocabulary at the ORM
    layer, though the two vocabularies remain conceptually distinct
    (pre-existing gap, not closed by this PR — see the PR9 apply
    report).
  - ``envio_dian.fecha_retencion_hasta`` exists in the migration but
    isn't redeclared in the ORM class — stamped via raw SQL UPDATE.
  - ``Alerta`` lacks ``uuid_cadena_raiz`` / ``uuid_referencia``;
    ``uuid_alerta_padre=None`` (chain root) and ``uuid_arqueo=<envio.uuid>``
    (reference back) preserve today's state-machine contract.

Issuer: cloud-only (module-level import guard).
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import uuid as uuid_lib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# T-PR11-07 — DIAN boundary layer 2: branch deploys bail at module load.
if os.environ.get("PARKOS_DEPLOY", "cloud").lower() == "branch":
    raise ImportError(
        "dian_cloud_unavailable_on_branch (T-PR11-07, REQ-X3, design §10 Layer 2)"
    )

from ...models.A.revocacion_factura import RevocacionFactura
from ...models.L_E.factura_electronica import FacturaElectronica
from ...models.L_W.alerta import Alerta
from ...models.L_W.envio_dian import EnvioDian
from ...models.V.resolucion_facturacion import ResolucionFacturacion
from ...repo import alert_types
from ...repo.append_only import append_event
from ...sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME
from ...sync.hooks.base import HookContext
from ..backoff import DIAN_BACKOFF_SCHEDULE, DIAN_MAX_RETRIES
from .dian_providers.factus import DianProvider, FactusProvider, PollResult
from .ubl_serializer import serialize

# --- Polling/retry schedule (T-PR11-01) ---
_POLL_INTERVAL_S: float = 2.0
_BACKOFF_5XX_SECONDS: tuple[int, ...] = (60, 300, 900)  # 1m, 5m, 15m
_DEFAULT_TIMEOUT_S = 30
_DEFAULT_RETRY_MAX = 3
_DIAN_RETENTION_YEARS = 5
ESTADO_ACEPTADO, ESTADO_RECHAZADO, ESTADO_TIMEOUT, ESTADO_EN_PROCESO = (
    "aceptado",
    "rechazado",
    "timeout",
    "en_proceso",
)
# T-PR9-008 — terminal outcome after the outer DIAN_BACKOFF_SCHEDULE retry
# budget (DIAN_MAX_RETRIES attempts) is exhausted with no ``aceptado``.
# Distinct from ESTADO_TIMEOUT (one attempt's own poll budget elapsed) —
# ESTADO_ERROR means the WHOLE retry budget, across multiple attempts, is
# spent.
ESTADO_ERROR = "error"


def _now_naive() -> datetime:
    """Naive UTC ``datetime`` — matches ``repo/versioned.py`` style."""
    return datetime.now(UTC).replace(tzinfo=None)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _env_int_pos(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, str(default))))
    except ValueError:
        return default


def _http_motivo(prefix: str, exc: httpx.HTTPStatusError) -> str:
    try:
        body = (exc.response.text or "").strip()
    except (httpx.HTTPError, ValueError):
        body = "<unreadable>"
    return f"{prefix} HTTP {exc.response.status_code}: {body}"[:1000]


async def _do_poll_once(provider: DianProvider, track_id: str) -> PollResult:
    """HTTPStatusError → ``rechazado``; RequestError → ``en_proceso`` (keep polling)."""
    try:
        return await provider.poll(track_id)
    except httpx.HTTPStatusError as exc:
        return PollResult(
            estado=ESTADO_RECHAZADO, motivo_rechazo=_http_motivo("poll:", exc)
        )
    except httpx.RequestError:
        return PollResult(estado=ESTADO_EN_PROCESO)


async def _send_initial(
    provider: DianProvider, xml_bytes: bytes
) -> tuple[str | None, PollResult | None]:
    """``(track_id, None)`` on success; ``(None, rechazo)`` on HTTP rejection.

    Transport-level errors (``httpx.RequestError`` — connection refused,
    read timeout, etc.) are wrapped in the ``backoff_5xx`` retry loop
    per §21.11 step 6: ``[60, 300, 900]`` seconds between attempts,
    up to ``PARKOS_DIAN_RETRY_MAX`` retries. On exhaustion the function
    surfaces a ``timeout`` :class:`PollResult` so the caller routes to
    :func:`_record_terminal`, which writes the ``dian_timeout`` alerta
    chain root + stamps ``respuesta_proveedor.estado_dian='timeout'``.

    PR11c — Bug 3 closes the gap from PR11a where these errors
    propagated as uncaught ``httpx.ConnectTimeout`` /
    ``httpx.ReadTimeout`` exceptions, leaving the envio_dian row in
    ``pendiente`` state with no operator-visible alerta.
    """
    retry_max = _env_int_pos("PARKOS_DIAN_RETRY_MAX", _DEFAULT_RETRY_MAX)
    last_exc: httpx.RequestError | None = None
    for attempt_idx in range(retry_max + 1):
        try:
            return await provider.send_ubl(xml_bytes), None
        except httpx.HTTPStatusError as exc:
            return None, PollResult(
                estado=ESTADO_RECHAZADO, motivo_rechazo=_http_motivo("send:", exc)
            )
        except httpx.RequestError as exc:
            last_exc = exc
            # Sleep ``backoff_5xx[min(attempt_idx, 2)]`` before the next
            # attempt. The schedule mirrors the poll-side retry loop so
            # the two paths use the same wait math.
            if attempt_idx < retry_max:
                backoff_idx = min(attempt_idx, len(_BACKOFF_5XX_SECONDS) - 1)
                await asyncio.sleep(_BACKOFF_5XX_SECONDS[backoff_idx])
    # Exhaustion — surface as a timeout rejection; the caller routes to
    # ``_record_terminal`` which stamps ``envio_dian`` and emits the
    # ``dian_timeout`` alerta chain root.
    motivo = f"send: {type(last_exc).__name__ if last_exc else 'RequestError'}: timeout"
    return None, PollResult(estado=ESTADO_TIMEOUT, motivo_rechazo=motivo)


async def _write_alerta(
    session: AsyncSession,
    *,
    uuid_sucursal: uuid_lib.UUID | None,
    uuid_arqueo: uuid_lib.UUID | None,
    tipo_alerta: str,
) -> None:
    """Chain-root alerta (design §21.11), validated against ``prod.alert_types``.

    T-PR9 retrofit: ``repo/alert_types.py`` (T-PR8-002) documents this
    call site as a "pre-existing alert-writing call site predating
    prod.alert_types entirely" whose retrofit is "a documented, explicitly
    out-of-scope follow-up for whichever PR next touches those modules" —
    this PR touches this module (T-PR9-003/008 add ``fe_numbering_exhausted``
    / ``fe_provider_error``), so the retrofit lands here.

    Uses ``append_event`` (Alerta is [L-W] not [A] so the static TypeVar
    bound to AppendOnlyBase is a narrow only — runtime is generic INSERT).

    Args:
        uuid_sucursal: Tenant scope for the alert.
        uuid_arqueo: Reference back into the row this alert is about
            (an ``envio_dian`` row for a dispatch outcome, or a
            ``factura_electronica`` row for a range violation — the
            column name is historical, not a literal ``arqueo`` FK).
        tipo_alerta: Must be a registered ``prod.alert_types`` identifier.
    """
    await alert_types.validate(session, tipo_alerta)
    attrs: dict[str, Any] = {
        "uuid_sucursal": uuid_sucursal,
        "tipo_alerta": tipo_alerta,
        "uuid_alerta_padre": None,  # chain root
        "uuid_arqueo": uuid_arqueo,  # reference back
        "timestamp_evento": _now_naive(),
    }
    await append_event(session, Alerta, attrs)  # type: ignore[arg-type]


def _stamp_envio_retention_on_attribute(envio: EnvioDian) -> None:
    """Stamp the DIAN 5-year retention column on the ORM instance (PR11c -- Bug 4).

    Replaces the PR11a raw SQL ``UPDATE prod.envio_dian`` path with a
    straight attribute mutation -- ``EnvioDian.fecha_retencion_hasta``
    is now declared on the ORM class so the change flows through
    ``session.add(envio)`` like every other ORM write in the codebase.

    The caller (``_record_terminal``) commits once after both the
    retention stamp and the alerta INSERT land on the session, so no
    extra commit lives here.
    """
    envio.fecha_retencion_hasta = _now_naive().date() + timedelta(
        days=365 * _DIAN_RETENTION_YEARS
    )


async def _record_terminal(
    envio: EnvioDian, poll_result: PollResult, session: AsyncSession
) -> EnvioDian:
    """Stamp envio on terminal poll outcome + alerta on failure.

    DIAN outcome lives in ``respuesta_proveedor.estado_dian`` (the
    column built for the provider's reply); ``cufe`` writes go to the
    dedicated column. One commit covers envio UPDATE + alerta INSERT.
    """
    estado = poll_result.estado
    payload: dict[str, Any] = {"estado_dian": estado}
    if poll_result.cufe is not None:
        envio.cufe = poll_result.cufe
        payload["cufe"] = poll_result.cufe
    if poll_result.motivo_rechazo is not None:
        payload["motivo_rechazo"] = poll_result.motivo_rechazo
    envio.respuesta_proveedor = payload
    envio.timestamp_evento = _now_naive()
    # T-PR9-009 — the branch reads the DIAN outcome through the derived
    # view ``prod.v_factura_electronica_acuse`` (migration 0009,
    # T-PR5-008), which projects ``envio_dian.estado`` directly. Mirror
    # the SAME outcome value onto ``estado`` (not just
    # ``respuesta_proveedor.estado_dian``) so that view carries something
    # meaningful for the branch to read.
    envio.estado = estado

    if estado == ESTADO_ACEPTADO:
        _stamp_envio_retention_on_attribute(envio)
    elif estado == ESTADO_RECHAZADO:
        await _write_alerta(
            session,
            uuid_sucursal=envio.uuid_sucursal,
            uuid_arqueo=envio.uuid,
            tipo_alerta="dian_rechazada",
        )
    elif estado == ESTADO_TIMEOUT:
        await _write_alerta(
            session,
            uuid_sucursal=envio.uuid_sucursal,
            uuid_arqueo=envio.uuid,
            tipo_alerta="dian_timeout",
        )
    else:  # Unknown terminal → surface to operator.
        await _write_alerta(
            session,
            uuid_sucursal=envio.uuid_sucursal,
            uuid_arqueo=envio.uuid,
            tipo_alerta="dian_error",
        )
    await session.commit()
    await session.refresh(envio)
    return envio


class ConsecutivoRangeError(RuntimeError):
    """Raised when a ``factura_electronica``'s ``consecutivo`` falls
    outside its ``resolucion_facturacion``'s authorized range (T-PR9-003).
    """


async def validate_consecutivo_range(
    session: AsyncSession, *, factura: FacturaElectronica
) -> None:
    """Reject a document whose ``consecutivo`` is outside its resolution's range.

    Design.md §7.3: the cloud validates the branch-assigned ``consecutivo``
    on receipt, before forwarding to the DIAN provider. A missing
    resolution, a missing ``consecutivo``, or a value outside
    ``[rango_desde, rango_hasta]`` (whichever bounds are set) raises
    :class:`ConsecutivoRangeError` AND writes ``alerta
    tipo_alerta='fe_numbering_exhausted'`` — the branch has either
    exhausted its authorized range or something is corrupt; either way an
    operator must act (new resolution, or investigate).

    Raises:
        ConsecutivoRangeError: ``consecutivo`` is out of range (or the
            resolution / the value itself is missing).
    """
    resolucion = (
        await session.execute(
            select(ResolucionFacturacion).where(
                ResolucionFacturacion.uuid == factura.uuid_resolucion_facturacion
            )
        )
    ).scalar_one_or_none()

    consecutivo = factura.consecutivo
    rango_desde = resolucion.rango_desde if resolucion is not None else None
    rango_hasta = resolucion.rango_hasta if resolucion is not None else None

    out_of_range = (
        resolucion is None
        or consecutivo is None
        or (rango_desde is not None and consecutivo < rango_desde)
        or (rango_hasta is not None and consecutivo > rango_hasta)
    )
    if out_of_range:
        await _write_alerta(
            session,
            uuid_sucursal=factura.uuid_sucursal,
            uuid_arqueo=factura.uuid,
            tipo_alerta="fe_numbering_exhausted",
        )
        raise ConsecutivoRangeError(
            f"factura_electronica {factura.uuid} consecutivo={consecutivo!r} "
            f"outside resolucion_facturacion {factura.uuid_resolucion_facturacion} "
            f"authorized range [{rango_desde}, {rango_hasta}]"
        )


async def _poll_loop(
    provider: DianProvider, track_id: str, timeout_s: float
) -> PollResult | None:
    """Single-attempt poll loop. ``None`` ⇒ budget elapsed; keep state intact."""
    loop = asyncio.get_event_loop()
    started = loop.time()
    while True:
        elapsed = loop.time() - started
        if elapsed >= timeout_s:
            return None
        result = await _do_poll_once(provider, track_id)
        if result.estado != ESTADO_EN_PROCESO:
            return result
        await asyncio.sleep(min(_POLL_INTERVAL_S, timeout_s - elapsed))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def dispatch_factura_electronica(
    session: AsyncSession,
    *,
    uuid_factura_electronica: uuid_lib.UUID,
    actor_uuid: uuid_lib.UUID,
    dian_provider_url: str,
    dian_token_path: Path,
    parent_envio_uuid: uuid_lib.UUID | None = None,
) -> EnvioDian:
    """Send ``factura_electronica`` to DIAN; return the terminal ``envio_dian``.

    Raises ``RuntimeError`` if the source row is missing. Raises
    :class:`ConsecutivoRangeError` if the row's ``consecutivo`` falls
    outside its resolution's authorized range (T-PR9-003) — no HTTP call
    is made in that case. The terminal outcome (``aceptado`` |
    ``rechazado`` | ``timeout``) lives in ``respuesta_proveedor.estado_dian``
    of the returned row.

    Args:
        parent_envio_uuid: When set, chains the new ``envio_dian`` row to
            a prior attempt via ``uuid_envio_padre`` (T-PR9-008 — used by
            :func:`dispatch_factura_electronica_with_backoff` across
            retries). ``None`` (default) starts a fresh chain, matching
            this function's original single-attempt behavior.
    """
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

    await validate_consecutivo_range(session, factura=row)

    xml_bytes = serialize(row)
    xml_sha256 = hashlib.sha256(xml_bytes).hexdigest()
    provider: DianProvider = FactusProvider(
        base_url=dian_provider_url, token_path=dian_token_path
    )

    # Persist envio_dian BEFORE any HTTP work — a crash mid-dispatch
    # leaves a "pendiente" row a follow-up worker can resume. The
    # AFTER INSERT trigger enqueues sync_queue (PR2 §12).
    now = _now_naive()
    envio = EnvioDian(
        uuid_sucursal=row.uuid_sucursal,
        uuid_factura_electronica=row.uuid,
        uuid_resolucion_facturacion=row.uuid_resolucion_facturacion,
        payload={"xml_sha256": xml_sha256, "estado_dian": "pendiente"},
        uuid_envio_padre=parent_envio_uuid,
        timestamp_evento=now,
        created_at=now,
        created_by=actor_uuid,
    )
    session.add(envio)
    await session.flush()  # populate envio.uuid without committing

    # Initial POST. Rejected XML → rejection + alerta, no track_id.
    track_id, rechazo = await _send_initial(provider, xml_bytes)
    if rechazo is not None:
        return await _record_terminal(envio, rechazo, session)

    # Commit with track_id, then enter the poll loop.
    envio.payload = {**envio.payload, "track_id": track_id}  # type: ignore[dict-item]
    await session.commit()
    await session.refresh(envio)

    # Initial poll window.
    timeout_s = _env_float("PARKOS_DIAN_TIMEOUT_S", float(_DEFAULT_TIMEOUT_S))
    terminal = await _poll_loop(provider, track_id, timeout_s)  # type: ignore[arg-type]
    if terminal is not None:
        return await _record_terminal(envio, terminal, session)

    # Retry loop: each attempt sleeps backoff_5xx[min(i,2)] then runs
    # its OWN poll window of `timeout_s` seconds (same as initial).
    retry_max = _env_int_pos("PARKOS_DIAN_RETRY_MAX", _DEFAULT_RETRY_MAX)
    for attempt_idx in range(retry_max):
        backoff_idx = min(attempt_idx, len(_BACKOFF_5XX_SECONDS) - 1)
        await asyncio.sleep(_BACKOFF_5XX_SECONDS[backoff_idx])
        terminal = await _poll_loop(provider, track_id, timeout_s)  # type: ignore[arg-type]
        if terminal is not None:
            return await _record_terminal(envio, terminal, session)

    # All retries exhausted → final timeout outcome.
    return await _record_terminal(
        envio,
        PollResult(estado=ESTADO_TIMEOUT, motivo_rechazo="dian_poll_timeout"),
        session,
    )


async def dispatch_revocacion(
    session: AsyncSession,
    *,
    uuid_revocacion_factura: uuid_lib.UUID,
    actor_uuid: uuid_lib.UUID | None = None,
    dian_provider_url: str,
    dian_token_path: Path,
    parent_envio_uuid: uuid_lib.UUID | None = None,
) -> EnvioDian:
    """Send a ``revocacion_factura`` to DIAN (T-PR11-02, design §21.11 step 2).

    Args:
        parent_envio_uuid: When set, chains the new ``envio_dian`` row to
            a prior attempt via ``uuid_envio_padre`` (T-PR9-010 — used by
            :func:`dispatch_revocacion_with_backoff` across retries).

    Mirrors :func:`dispatch_factura_electronica` step-for-step so the
    two state machines stay symmetric and the existing helpers
    (``:func:`_poll_loop```, :func:`_record_terminal`, the ``ESTADO_*``
    constants) cover every branch. Differences:

    - POST goes to ``/api/revocacion`` (via
      :meth:`FactusProvider.send_revocacion`).
    - On ``aceptado`` the ``prod.revocacion_factura`` SHA-256 chain is
      extended via the catalog's ``hook_chain_extend`` slot
      (``RevocacionFacturaChain``, T-PR6-005) — the new row carries
      ``motivo='dian_confirmada'`` so it's distinguishable from the
      original webhook request. REQ-16 + REQ-X4.
    - On ``aceptado`` the branch learns the confirmation through the
      ORDINARY ``envio_dian`` ``cloud_to_branch`` catalog entry (D1-rev,
      design.md §0 amendment #1) — no separate outbound placeholder is
      enqueued here (T-PR9-007/008 removed the withdrawn one).

    Raises ``RuntimeError`` if the source revocation row is missing.
    The terminal outcome (``aceptado`` | ``rechazado`` | ``timeout``)
    lives in ``respuesta_proveedor.estado_dian`` of the returned row.
    """
    # 1. Load the source row.
    row = (
        await session.execute(
            select(RevocacionFactura).where(
                RevocacionFactura.uuid == uuid_revocacion_factura
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise RuntimeError(
            f"revocacion_factura {uuid_revocacion_factura} not found"
        )

    # 2. Serialize to UBL XML. TODO(T-PR11c): replace with
    # ``ubl_serializer.serialize_revocacion(row)`` once that helper lands.
    # The current ``ubl_serializer.serialize`` handles ``FacturaElectronica``
    # only; do not expand its scope in this PR.
    xml_bytes = b"<revocation-stub/>"
    xml_sha256 = hashlib.sha256(xml_bytes).hexdigest()
    provider: DianProvider = FactusProvider(
        base_url=dian_provider_url, token_path=dian_token_path
    )

    # 3 + 4. Persist envio_dian BEFORE any HTTP work; a crash mid-dispatch
    # leaves a "pendiente" row a follow-up worker can resume. The
    # ``AFTER INSERT`` trigger enqueues sync_queue (PR2 §12). The source
    # revocation's uuid lives in ``payload`` (no dedicated FK column on
    # envio_dian).
    now = _now_naive()
    envio = EnvioDian(
        uuid_sucursal=row.uuid_sucursal,
        uuid_factura_electronica=row.uuid_factura_electronica,
        payload={
            "xml_sha256": xml_sha256,
            "estado_dian": "pendiente",
            "uuid_revocacion_factura": str(row.uuid),
        },
        uuid_envio_padre=parent_envio_uuid,
        timestamp_evento=now,
        created_at=now,
        created_by=actor_uuid,
    )
    session.add(envio)
    await session.flush()  # populate envio.uuid without committing

    # Initial POST — rejection short-circuits straight to terminal.
    try:
        track_id = await provider.send_revocacion(xml_bytes)
    except httpx.HTTPStatusError as exc:
        return await _record_terminal(
            envio,
            PollResult(
                estado=ESTADO_RECHAZADO, motivo_rechazo=_http_motivo("send:", exc)
            ),
            session,
        )

    # Commit with track_id, then enter the poll loop.
    envio.payload = {**envio.payload, "track_id": track_id}  # type: ignore[dict-item]
    await session.commit()
    await session.refresh(envio)

    # 5. Initial poll window.
    timeout_s = _env_float("PARKOS_DIAN_TIMEOUT_S", float(_DEFAULT_TIMEOUT_S))
    terminal: PollResult | None = await _poll_loop(provider, track_id, timeout_s)  # type: ignore[arg-type]
    if terminal is not None:
        return await _finalize_revocacion(envio, terminal, session, row, actor_uuid)

    # Retry loop: each attempt sleeps ``backoff_5xx[min(i,2)]`` then runs
    # its OWN poll window of ``timeout_s`` seconds (same as initial).
    retry_max = _env_int_pos("PARKOS_DIAN_RETRY_MAX", _DEFAULT_RETRY_MAX)
    for attempt_idx in range(retry_max):
        backoff_idx = min(attempt_idx, len(_BACKOFF_5XX_SECONDS) - 1)
        await asyncio.sleep(_BACKOFF_5XX_SECONDS[backoff_idx])
        terminal = await _poll_loop(provider, track_id, timeout_s)  # type: ignore[arg-type]
        if terminal is not None:
            return await _finalize_revocacion(
                envio, terminal, session, row, actor_uuid
            )

    # All retries exhausted → final timeout outcome.
    return await _finalize_revocacion(
        envio,
        PollResult(estado=ESTADO_TIMEOUT, motivo_rechazo="dian_poll_timeout"),
        session,
        row,
        actor_uuid,
    )


async def _finalize_revocacion(
    envio: EnvioDian,
    terminal: PollResult,
    session: AsyncSession,
    row: RevocacionFactura,
    actor_uuid: uuid_lib.UUID | None,
) -> EnvioDian:
    """Stamp envio + (on ``aceptado``) extend the SHA-256 chain.

    The envio+alerta+retention stamp runs through the shared
    :func:`_record_terminal` helper (one commit). On ``aceptado`` we
    ADDITIONALLY extend the ``prod.revocacion_factura`` SHA-256 chain in a
    second commit — the original ``_record_terminal`` already committed
    the DIAN ack, so a chain-extension failure surfaces as a DB error
    from the cloud-side verifier (PR10) instead of losing the ack.

    D1-rev (design.md §0 amendment #1): the branch learns the DIAN ack
    arrived through the ORDINARY ``envio_dian`` ``cloud_to_branch``
    catalog entry, via the ``AFTER INSERT`` trigger `_record_terminal`'s
    commit already fires (PR2 §12) — no separate sync_queue placeholder
    is needed or written here (T-PR9-007/008 removed it; it predated this
    PR and was never the shipped design).
    """
    envio = await _record_terminal(envio, terminal, session)

    if terminal.estado == ESTADO_ACEPTADO:
        # 7. Extend the SHA-256 chain — the cloud-side confirmation row.
        # ``motivo='dian_confirmada'`` distinguishes this row from the
        # original webhook-originated row (whose motivo is the DIAN
        # payload's motive string). T-PR6-005: looks up the catalog's
        # ``hook_chain_extend`` slot (``RevocacionFacturaChain``) instead of
        # calling ``repo.hash_chain.append`` directly — the extension logic
        # itself is unchanged, but is now reached via the SAME catalog-
        # registered hook every other caller uses (design.md §6).
        chain_payload: dict[str, Any] = {
            "uuid_sucursal": row.uuid_sucursal,
            "uuid_factura_electronica": row.uuid_factura_electronica,
            "uuid_factura_electronica_reemplazo": (
                row.uuid_factura_electronica_reemplazo
            ),
            "motivo": "dian_confirmada",
            "timestamp_evento": _now_naive(),
        }
        revocacion_spec = SYNC_CATALOG_BY_NAME["revocacion_factura"]
        chain_hook = revocacion_spec.hook_chain_extend
        assert chain_hook is not None, (
            "revocacion_factura catalog entry has no hook_chain_extend bound"
        )
        await chain_hook(
            HookContext(
                spec=revocacion_spec,
                payload=chain_payload,
                session=session,
                actor_uuid=actor_uuid or uuid_lib.uuid4(),
            )
        )
        await session.commit()

    return envio


# ---------------------------------------------------------------------------
# T-PR9-008/010 — outer DIAN_BACKOFF_SCHEDULE retry budget
# ---------------------------------------------------------------------------


def _terminal_estado_dian(envio: EnvioDian) -> str | None:
    """Read back the outcome :func:`_record_terminal` just stamped."""
    if envio.respuesta_proveedor is None:
        return None
    return envio.respuesta_proveedor.get("estado_dian")


async def _mark_provider_error_exhausted(
    session: AsyncSession, envio: EnvioDian
) -> EnvioDian:
    """Stamp the outer retry budget as exhausted (design.md §2 Issue #9).

    Distinct from a single attempt's own ``ESTADO_TIMEOUT``/
    ``ESTADO_RECHAZADO`` — this fires once the WHOLE
    ``DIAN_BACKOFF_SCHEDULE`` budget (``DIAN_MAX_RETRIES`` attempts) is
    spent with no ``aceptado``. Raises the critical, budget-exhaustion
    alert (``fe_provider_error``) distinct from any per-attempt alert
    already written by :func:`_record_terminal`.
    """
    envio.respuesta_proveedor = {
        **(envio.respuesta_proveedor or {}),
        "estado_dian": ESTADO_ERROR,
    }
    envio.estado = ESTADO_ERROR
    await _write_alerta(
        session,
        uuid_sucursal=envio.uuid_sucursal,
        uuid_arqueo=envio.uuid,
        tipo_alerta="fe_provider_error",
    )
    await session.commit()
    await session.refresh(envio)
    return envio


async def dispatch_factura_electronica_with_backoff(
    session: AsyncSession,
    *,
    uuid_factura_electronica: uuid_lib.UUID,
    actor_uuid: uuid_lib.UUID,
    dian_provider_url: str,
    dian_token_path: Path,
    max_retries: int = DIAN_MAX_RETRIES,
) -> EnvioDian:
    """Drive :func:`dispatch_factura_electronica` across the DIAN retry budget.

    Each attempt is one full send+poll round trip, chained to the prior
    attempt via ``uuid_envio_padre`` (the ``envio_dian`` catalog entry
    declares ``self_chain=True``). A non-``aceptado`` terminal outcome
    waits ``DIAN_BACKOFF_SCHEDULE[attempt]`` (T-PR9-004) before the next
    attempt. After ``max_retries`` attempts with no ``aceptado``, the
    LAST envio row is stamped ``estado='error'`` /
    ``estado_dian='error'`` and ``alerta tipo_alerta='fe_provider_error'``
    fires (T-PR9-008).

    The single-attempt function's OWN internal transport retry
    (``_send_initial``/``_poll_loop``, ``PARKOS_DIAN_RETRY_MAX``) is
    untouched and runs INSIDE each attempt here — this is a SEPARATE,
    outer retry layer.
    """
    parent_uuid: uuid_lib.UUID | None = None
    envio: EnvioDian | None = None
    for attempt in range(max_retries):
        envio = await dispatch_factura_electronica(
            session,
            uuid_factura_electronica=uuid_factura_electronica,
            actor_uuid=actor_uuid,
            dian_provider_url=dian_provider_url,
            dian_token_path=dian_token_path,
            parent_envio_uuid=parent_uuid,
        )
        if _terminal_estado_dian(envio) == ESTADO_ACEPTADO:
            return envio
        parent_uuid = envio.uuid
        if attempt < max_retries - 1:
            await asyncio.sleep(DIAN_BACKOFF_SCHEDULE[attempt].total_seconds())

    assert envio is not None  # max_retries >= 1 (DIAN_MAX_RETRIES == 6)
    return await _mark_provider_error_exhausted(session, envio)


async def dispatch_revocacion_with_backoff(
    session: AsyncSession,
    *,
    uuid_revocacion_factura: uuid_lib.UUID,
    actor_uuid: uuid_lib.UUID | None = None,
    dian_provider_url: str,
    dian_token_path: Path,
    max_retries: int = DIAN_MAX_RETRIES,
) -> EnvioDian:
    """Drive :func:`dispatch_revocacion` across the DIAN retry budget.

    Mirrors :func:`dispatch_factura_electronica_with_backoff` — T-PR9-010:
    ``revocacion_factura`` reuses the EXACT SAME ``DIAN_BACKOFF_SCHEDULE``,
    ``max_retries``, and ``on_exhaustion`` alert as ``factura_electronica``
    (same DIAN evidentiary chain, same regulatory deadline).
    """
    parent_uuid: uuid_lib.UUID | None = None
    envio: EnvioDian | None = None
    for attempt in range(max_retries):
        envio = await dispatch_revocacion(
            session,
            uuid_revocacion_factura=uuid_revocacion_factura,
            actor_uuid=actor_uuid,
            dian_provider_url=dian_provider_url,
            dian_token_path=dian_token_path,
            parent_envio_uuid=parent_uuid,
        )
        if _terminal_estado_dian(envio) == ESTADO_ACEPTADO:
            return envio
        parent_uuid = envio.uuid
        if attempt < max_retries - 1:
            await asyncio.sleep(DIAN_BACKOFF_SCHEDULE[attempt].total_seconds())

    assert envio is not None  # max_retries >= 1 (DIAN_MAX_RETRIES == 6)
    return await _mark_provider_error_exhausted(session, envio)


__all__ = [
    "ConsecutivoRangeError",
    "DianProvider",
    "EnvioDian",
    "FactusProvider",
    "PollResult",
    "dispatch_factura_electronica",
    "dispatch_factura_electronica_with_backoff",
    "dispatch_revocacion",
    "dispatch_revocacion_with_backoff",
    "validate_consecutivo_range",
]
