"""UBL 2.1 XML serializer for ``factura_electronica`` rows (T-PR11-03).

Minimal XML builder. The full ``lxml`` + XSD-validated implementation
(against ``xsd/UBL-Invoice-2.1.xsd``) lands with the follow-up PR that
also ships ``tests/dian/test_ubl_serializer.py`` (T-PR11-13) — ``lxml``
is not yet a declared dependency of ``parkos-core``, so this module
stays on the stdlib.

Scope note: ``prod.factura_electronica`` holds only the DIAN identity
of the document (``prefijo``, ``consecutivo``, ``uuid_resolucion_facturacion``)
plus the FK to ``prod.facturas``. Lines, taxes, and totals live on the
related ``facturas`` / ``factura_detalle`` rows and are resolved by the
follow-up PR; this serializer emits the document header only.

Issuer: cloud-only (module-level import guard below).
"""
from __future__ import annotations

import os
from datetime import UTC, datetime
from xml.sax.saxutils import escape

# Module-level import guard (T-PR11-07 — DIAN boundary layer 2).
# Kept as the first non-stdlib statement so branch deploys fail at
# module load, before any ORM import runs.
if os.environ.get("PARKOS_DEPLOY", "cloud").lower() == "branch":
    raise ImportError(
        "dian_cloud_unavailable_on_branch (T-PR11-07, REQ-X3, design §10 Layer 2)"
    )

from ...models.L_E.factura_electronica import FacturaElectronica

# UBL 2.1 namespaces.
_NS = {
    "xmlns": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
}

# Fallback prefix when the resolution carries none. DIAN's sandbox
# prefix; a production row always resolves ``prefijo`` from
# ``resolucion_facturacion`` before reaching this serializer.
_DEFAULT_PREFIJO = "SETP"

_CURRENCY_CODE = "COP"


def serialize(factura: FacturaElectronica) -> bytes:
    """Build a UBL 2.1 XML payload from a ``factura_electronica`` row.

    Args:
        factura: The ``[L-E]`` row to serialize. Only header fields are
            read; the row is never mutated.

    Returns:
        UTF-8 encoded XML bytes, ready to POST to the DIAN provider.
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    inv_id = str(factura.uuid)
    created_at = factura.created_at or now
    issue_date = created_at.date().isoformat()
    consecutivo = factura.consecutivo or 0
    prefijo = factura.prefijo or _DEFAULT_PREFIJO
    doc_number = escape(f"{prefijo}{consecutivo}")

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<Invoice xmlns="{_NS["xmlns"]}" '
            f'xmlns:cac="{_NS["cac"]}" xmlns:cbc="{_NS["cbc"]}">'
        ),
        "  <cbc:UBLVersionID>2.1</cbc:UBLVersionID>",
        "  <cbc:CustomizationID>parkos-1.0</cbc:CustomizationID>",
        f"  <cbc:ID>{doc_number}</cbc:ID>",
        f"  <cbc:IssueDate>{issue_date}</cbc:IssueDate>",
        f"  <cbc:DocumentCurrencyCode>{_CURRENCY_CODE}</cbc:DocumentCurrencyCode>",
        f"  <cac:InvoiceUUID>{inv_id}</cac:InvoiceUUID>",
        "  <cac:AccountingSupplierParty>",
        "    <cbc:AdditionalAccountID>parkos</cbc:AdditionalAccountID>",
        "  </cac:AccountingSupplierParty>",
        "</Invoice>",
    ]
    return "\n".join(lines).encode("utf-8")


__all__ = ["serialize"]
