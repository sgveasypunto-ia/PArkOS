"""[L-W] Workflow ORM models (design \u00a73.1 + \u00a74.2 state machines).

PR6 ships six workflow tables:

  - :class:`ReimpresionTicket`  - ticket reprint chain (branch)
  - :class:`Anulaciones`        - ingreso/salida annulment chain (branch, partitioned)
  - :class:`Reclamos`           - polymorphic claim against ingreso/salida/factura (branch)
  - :class:`Alerta`             - cash-count anomaly (branch, partitioned)
  - :class:`EnvioDian`          - DIAN send/ack workflow (cloud-only)
  - :class:`ValidacionEvento`   - admin validation of received events (cloud-only)

All classes descend from :class:`WorkflowBase`. The migration adds
``vigente_desde`` / ``vigente_hasta`` / ``estado`` via
``*_versioning_columns()``; each concrete class re-declares them
explicitly (mirroring the ``HashChainMixin`` pattern in
``models/A/log_transaccional.py``) because ``WorkflowBase`` does not
inherit :class:`VersionedMixin`. Transitions flow through
:mod:`parkos_core.repo.workflow` which performs the ``close + insert``
dance co-transactional with a ``log_transaccional`` row
(REQ-21, REQ-X9).
"""
from __future__ import annotations

__all__: list[str] = []