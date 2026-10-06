"""Project-wide constants shared by migrations, repo helpers and tests.

CLIENTE ESTANDAR (consumidor final)
-----------------------------------
Every electronic invoice is always emitted. When the payer does not ask
for an invoice in their own name, the document is issued to a "cliente
estandar" (DIAN generic consumer). The row is seeded by migration 0088 in
EVERY node (cloud and each branch) with the SAME deterministic uuid and the
SAME constant ``vigente_desde`` so ``identity_reconciler`` treats the
replicated copy as a no-op.

[POR DEFINIR] with accounting / the DIAN provider (Factus): identification
number, identifier type code and display name below are the agreed
working values, not yet validated by the provider.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime

# Same continuous uuid5 namespace as migrations 0019/0020/0056/0059/0066/0086.
UUID_NAMESPACE = uuid_lib.UUID("a3f1c9d4-6b2e-4e8a-9c1a-7d5f2b8e4c60")

# uuid5(UUID_NAMESPACE, "cliente_estandar_consumidor_final"), computed offline.
CLIENTE_ESTANDAR_UUID = uuid_lib.UUID("5e60b3e6-000a-5fdc-8dd7-d27a80c10e96")

# Natural person -- deterministic uuid seeded by migration 0020.
TIPO_PERSONA_NATURAL_UUID = uuid_lib.UUID("9ff893fd-e771-5b6a-8b18-6648e47c69d9")

CLIENTE_ESTANDAR_TIPO_IDENTIFICADOR = "CC"  # [POR DEFINIR]
CLIENTE_ESTANDAR_NUMERO_IDENTIFICACION = "222222222222"  # DIAN consumidor final
CLIENTE_ESTANDAR_NOMBRE = "Consumidor final"

# Constant valid-from: part of the row's identity, MUST be identical in every
# node (never ``now()``), otherwise the reconciler would see two versions.
CLIENTE_ESTANDAR_VIGENTE_DESDE = datetime(2026, 1, 1, 0, 0, 0)  # noqa: DTZ001 - naive UTC by project convention

__all__ = [
    "CLIENTE_ESTANDAR_NOMBRE",
    "CLIENTE_ESTANDAR_NUMERO_IDENTIFICACION",
    "CLIENTE_ESTANDAR_TIPO_IDENTIFICADOR",
    "CLIENTE_ESTANDAR_UUID",
    "CLIENTE_ESTANDAR_VIGENTE_DESDE",
    "TIPO_PERSONA_NATURAL_UUID",
    "UUID_NAMESPACE",
]
