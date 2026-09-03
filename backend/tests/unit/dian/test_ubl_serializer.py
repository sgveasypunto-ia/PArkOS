"""test_ubl_serializer.py -- T-PR11-13 (UBL 2.1 serializer tests).

The bundled UBL 2.1 XSD set (UBL-Invoice-2.1.xsd + 13 transitive
imports under maindoc/ + common/) lives in
``parkos_core/dian/cloud/xsd/``. The schema is loaded with NO network
access -- ``lxml`` resolves every ``schemaLocation`` via the local
relative paths the OASIS distribution already uses, so the test runs
fully offline (per tasks.md T-PR11-13 canon: "bundled in repo, NOT a
network fetch").

Two tests:

1. ``test_ubl_serialize_has_correct_namespaces_and_root`` -- primary
   regression test; structural assertions on the UBL 2.1 Invoice
   envelope (root + namespaces + the header child elements the XSD
   permits at the serializer's current scope).

2. ``test_ubl_serialize_validates_against_xsd`` -- ``@pytest.mark.xfail``
   acceptance gate for the PR11c follow-up that ships the full
   XSD-valid serializer (per the ``ubl_serializer`` module docstring:
   "The full lxml + XSD-validated implementation lands with the
   follow-up PR"). The current minimal serializer emits
   ``<cac:InvoiceUUID>``, which is not in the UBL 2.1 InvoiceType,
   so XSD validation cannot pass yet. The bundled XSD means once
   PR11c replaces the minimal builder the test starts passing
   without further wiring -- remove the ``xfail`` decorator then.

No database, no network at test runtime. The ``serialize`` call
reads only ``uuid`` / ``created_at`` / ``prefijo`` / ``consecutivo``
from the ``FacturaElectronica`` row, so the mock only populates
those four fields.
"""
from __future__ import annotations

import os
import uuid as uuid_lib
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from lxml import etree

# ---------------------------------------------------------------------------
# Parkos cloud-import guard (T-PR11-07 -- REQ-X3, design section 10 Layer 2).
# Mirror the dispatcher conftest pattern: stamp PARKOS_DEPLOY=cloud for the
# import window only, then restore. ``ubl_serializer`` is a cloud-only
# module; loading it on a branch deploy raises ImportError.
# ---------------------------------------------------------------------------
_PREV_DEPLOY = os.environ.get("PARKOS_DEPLOY")
os.environ["PARKOS_DEPLOY"] = "cloud"
try:
    from parkos_core.dian.cloud.ubl_serializer import serialize
finally:
    if _PREV_DEPLOY is None:
        os.environ.pop("PARKOS_DEPLOY", None)
    else:
        os.environ["PARKOS_DEPLOY"] = _PREV_DEPLOY


# Bundled XSD location. The path is fixed by repo layout:
# tests/unit/dian/test_ubl_serializer.py  ->  parents[3] == backend/
_XSD_MAIN_PATH = (
    Path(__file__).resolve().parents[3]
    / "packages"
    / "parkos_core"
    / "src"
    / "parkos_core"
    / "dian"
    / "cloud"
    / "xsd"
    / "maindoc"
    / "UBL-Invoice-2.1.xsd"
)


# ---------------------------------------------------------------------------
# Test doubles -- exactly what the minimal serializer reads today.
# ---------------------------------------------------------------------------


def _build_factura_mock() -> MagicMock:
    """Fully-populated ``FacturaElectronica``-like mock.

    The minimal serializer reads only ``uuid`` + ``created_at`` +
    ``prefijo`` + ``consecutivo``; everything else can stay at the
    ``MagicMock`` default.
    """
    row = MagicMock(name="FacturaElectronica")
    row.uuid = uuid_lib.UUID("00000000-0000-0000-0000-000000000001")
    row.prefijo = "SETP"
    row.consecutivo = 990000001
    row.created_at = datetime(2026, 1, 15, tzinfo=UTC).replace(tzinfo=None)
    return row


# ---------------------------------------------------------------------------
# 1. Primary structural test -- Note 3 fallback pattern. Passes today.
# ---------------------------------------------------------------------------


def test_ubl_serialize_has_correct_namespaces_and_root() -> None:
    """``serialize()`` emits a UBL 2.1 Invoice envelope with the right namespaces
    and the header child elements the XSD permits at the current scope.

    Asserted on the root tag (Clark form, full namespace URI), the bound
    ``cac`` / ``cbc`` prefixes, and the five header elements the
    serializer emits today (``UBLVersionID``, ``CustomizationID``, ``ID``,
    ``IssueDate``, ``DocumentCurrencyCode``) plus the
    ``AccountingSupplierParty`` envelope.
    """
    factura = _build_factura_mock()
    xml_bytes = serialize(factura)

    doc = etree.fromstring(xml_bytes)

    # Root: UBL 2.1 Invoice + cac + cbc namespaces.
    assert doc.tag == (
        "{urn:oasis:names:specification:ubl:schema:xsd:Invoice-2}Invoice"
    )
    cac_ns = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
    cbc_ns = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
    assert doc.nsmap["cac"] == cac_ns
    assert doc.nsmap["cbc"] == cbc_ns

    # Header children emitted by the minimal serializer.
    assert doc.find(f"{{{cbc_ns}}}UBLVersionID").text == "2.1"
    assert doc.find(f"{{{cbc_ns}}}CustomizationID").text == "parkos-1.0"
    assert doc.find(f"{{{cbc_ns}}}ID").text == "SETP990000001"
    assert doc.find(f"{{{cbc_ns}}}IssueDate").text == "2026-01-15"
    assert doc.find(f"{{{cbc_ns}}}DocumentCurrencyCode").text == "COP"

    # cac:AccountingSupplierParty envelope present.
    supplier = doc.find(f"{{{cac_ns}}}AccountingSupplierParty")
    assert supplier is not None


# ---------------------------------------------------------------------------
# 2. XSD-validation acceptance gate -- xfail pending PR11c.
# Remove the xfail decorator once the minimal serializer is expanded.
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    reason=(
        "UBL 2.1 XSD validation pending the PR11c follow-up that ships the "
        "full serializer (per ubl_serializer.py module docstring + "
        "openspec/changes/create-49-table-apis/tasks.md T-PR11c). The "
        "current minimal serializer emits <cac:InvoiceUUID> which is not "
        "in UBL 2.1 InvoiceType. When the full serializer lands, remove "
        "this xfail decorator -- the assertion will then pass against the "
        "already-bundled XSD."
    ),
    strict=False,
)
def test_ubl_serialize_validates_against_xsd() -> None:
    """``serialize()`` output validates against the bundled ``UBL-Invoice-2.1.xsd``.

    Acceptance gate for PR11c. The bundled XSD resolves every transitive
    ``schemaLocation`` via local file paths (no network access at test
    runtime). When the full UBL 2.1 serializer lands (replaces the
    ``<cac:InvoiceUUID>`` non-standard element with the proper
    ``<cbc:UUID>`` and adds ``AccountingCustomerParty`` + ``InvoiceLine``
    + ``TaxTotal`` + ``LegalMonetaryTotal``), remove the ``xfail``
    decorator and this test becomes a strict regression gate.
    """
    factura = _build_factura_mock()
    xml_bytes = serialize(factura)

    xsd_doc = etree.parse(str(_XSD_MAIN_PATH))
    schema = etree.XMLSchema(xsd_doc)

    xml_doc = etree.fromstring(xml_bytes)
    assert schema.validate(xml_doc), (
        f"UBL XML does not validate against UBL-Invoice-2.1.xsd. "
        f"Errors:\n{schema.error_log}"
    )
