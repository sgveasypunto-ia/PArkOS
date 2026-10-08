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
# 2. XSD-validation regression gate (PR11c -- Bug 1).
# The xfail decorator was REMOVED in PR11c once the full UBL 2.1
# serializer landed (lxml + UBLVersionID + InvoiceTypeCode + parties +
# TaxTotal + LegalMonetaryTotal + InvoiceLine). This test is now a
# hard regression check against ``UBL-Invoice-2.1.xsd`` -- any future
# serializer regression that breaks the XSD contract trips it.
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# 3. Customer party: real ``prod.clientes`` row, or the standard customer.
# ---------------------------------------------------------------------------

_CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
_CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"


def _customer_party(xml_bytes: bytes) -> tuple[str, str | None, str]:
    doc = etree.fromstring(xml_bytes)
    party = doc.find(f"{{{_CAC}}}AccountingCustomerParty/{{{_CAC}}}Party")
    ident = party.find(f"{{{_CAC}}}PartyIdentification/{{{_CBC}}}ID")
    name = party.find(f"{{{_CAC}}}PartyName/{{{_CBC}}}Name")
    return ident.text, ident.get("schemeName"), name.text


def test_ubl_customer_defaults_to_standard_customer() -> None:
    """No ``prod.clientes`` row -> the seeded standard customer, not the
    old ``consumidor_final`` placeholder."""
    from parkos_core.constants import (
        CLIENTE_ESTANDAR_NOMBRE,
        CLIENTE_ESTANDAR_NUMERO_IDENTIFICACION,
        CLIENTE_ESTANDAR_TIPO_IDENTIFICADOR,
    )

    numero, scheme, nombre = _customer_party(serialize(_build_factura_mock()))
    assert numero == CLIENTE_ESTANDAR_NUMERO_IDENTIFICACION
    assert scheme == CLIENTE_ESTANDAR_TIPO_IDENTIFICADOR
    assert nombre == CLIENTE_ESTANDAR_NOMBRE


def test_ubl_customer_uses_real_cliente_and_stays_xsd_valid() -> None:
    from types import SimpleNamespace

    cliente = SimpleNamespace(
        tipo_identificador="NIT",
        numero_identificacion="900111222",
        nombre="Acme",
        apellido="SAS",
    )
    xml_bytes = serialize(_build_factura_mock(), cliente)
    assert _customer_party(xml_bytes) == ("900111222", "NIT", "Acme SAS")

    schema = etree.XMLSchema(etree.parse(str(_XSD_MAIN_PATH)))
    assert schema.validate(etree.fromstring(xml_bytes)), schema.error_log


def test_ubl_standard_customer_is_xsd_valid() -> None:
    schema = etree.XMLSchema(etree.parse(str(_XSD_MAIN_PATH)))
    assert schema.validate(etree.fromstring(serialize(_build_factura_mock())))


# ---------------------------------------------------------------------------
# 4. Real totals: lines + tax detail from ``factura_detalle`` / ``factura_impuestos``.
# Subscription sale: the plan price (120000) is IVA-INCLUDED, so the base is
# 100840.34, the IVA 19159.66 and the payable amount the plan price.
# ---------------------------------------------------------------------------


def _suscripcion_detalles() -> list:
    from types import SimpleNamespace

    return [
        SimpleNamespace(
            concepto="subscripcion_mensual",
            cantidad=1,
            valor_unitario=100840.34,
            subtotal=100840.34,
        )
    ]


def _suscripcion_impuestos() -> list:
    from types import SimpleNamespace

    return [
        SimpleNamespace(
            codigo="IVA",
            nombre="IVA",
            base_calculo=100840.34,
            porcentaje_aplicado=0.19,
            valor=19159.66,
        )
    ]


def _xp(doc: etree._Element, path: str) -> list[etree._Element]:
    return doc.xpath(path, namespaces={"cac": _CAC, "cbc": _CBC})


def test_ubl_emits_tax_detail_and_reconciling_totals() -> None:
    xml_bytes = serialize(
        _build_factura_mock(),
        None,
        detalles=_suscripcion_detalles(),
        impuestos=_suscripcion_impuestos(),
    )
    doc = etree.fromstring(xml_bytes)

    assert _xp(doc, "/*/cac:TaxTotal/cbc:TaxAmount")[0].text == "19159.66"
    sub = _xp(doc, "/*/cac:TaxTotal/cac:TaxSubtotal")
    assert len(sub) == 1
    assert _xp(sub[0], "cbc:TaxableAmount")[0].text == "100840.34"
    assert _xp(sub[0], "cbc:TaxAmount")[0].text == "19159.66"
    assert _xp(sub[0], "cac:TaxCategory/cbc:Percent")[0].text == "19.00"
    assert _xp(sub[0], "cac:TaxCategory/cac:TaxScheme/cbc:ID")[0].text == "01"
    assert _xp(sub[0], "cac:TaxCategory/cac:TaxScheme/cbc:Name")[0].text == "IVA"

    base = _xp(doc, "/*/cac:LegalMonetaryTotal/cbc:LineExtensionAmount")[0].text
    excl = _xp(doc, "/*/cac:LegalMonetaryTotal/cbc:TaxExclusiveAmount")[0].text
    incl = _xp(doc, "/*/cac:LegalMonetaryTotal/cbc:TaxInclusiveAmount")[0].text
    payable = _xp(doc, "/*/cac:LegalMonetaryTotal/cbc:PayableAmount")[0].text
    assert (base, excl, incl, payable) == ("100840.34", "100840.34", "120000.00", "120000.00")

    # Line: description, quantity, base, and its own tax.
    line = _xp(doc, "/*/cac:InvoiceLine")
    assert len(line) == 1
    assert _xp(line[0], "cbc:LineExtensionAmount")[0].text == "100840.34"
    assert _xp(line[0], "cac:Item/cbc:Name")[0].text == "subscripcion_mensual"
    assert _xp(line[0], "cac:TaxTotal/cbc:TaxAmount")[0].text == "19159.66"
    assert _xp(line[0], "cac:TaxTotal/cac:TaxSubtotal/cbc:TaxableAmount")[0].text == "100840.34"


def test_ubl_with_tax_detail_stays_xsd_valid() -> None:
    xml_bytes = serialize(
        _build_factura_mock(),
        None,
        detalles=_suscripcion_detalles(),
        impuestos=_suscripcion_impuestos(),
    )
    schema = etree.XMLSchema(etree.parse(str(_XSD_MAIN_PATH)))
    assert schema.validate(etree.fromstring(xml_bytes)), schema.error_log


def test_ubl_line_taxes_sum_to_document_tax_across_several_lines() -> None:
    from types import SimpleNamespace

    detalles = [
        SimpleNamespace(concepto="a", cantidad=1, valor_unitario=33.33, subtotal=33.33),
        SimpleNamespace(concepto="b", cantidad=2, valor_unitario=33.33, subtotal=66.66),
        SimpleNamespace(concepto="c", cantidad=1, valor_unitario=0.01, subtotal=0.01),
    ]
    impuestos = [
        SimpleNamespace(
            codigo="IVA", nombre="IVA", base_calculo=100.00,
            porcentaje_aplicado=0.19, valor=19.00,
        )
    ]
    doc = etree.fromstring(serialize(_build_factura_mock(), None, detalles=detalles, impuestos=impuestos))
    from decimal import Decimal

    line_taxes = [Decimal(e.text) for e in _xp(doc, "/*/cac:InvoiceLine/cac:TaxTotal/cbc:TaxAmount")]
    assert len(line_taxes) == 3
    assert sum(line_taxes) == Decimal("19.00")
    assert _xp(doc, "/*/cac:LegalMonetaryTotal/cbc:PayableAmount")[0].text == "119.00"


def test_ubl_without_tax_rows_has_zero_tax_and_payable_equals_base() -> None:
    doc = etree.fromstring(
        serialize(_build_factura_mock(), None, detalles=_suscripcion_detalles(), impuestos=[])
    )
    assert _xp(doc, "/*/cac:TaxTotal/cbc:TaxAmount")[0].text == "0.00"
    assert _xp(doc, "/*/cac:TaxTotal/cac:TaxSubtotal") == []
    assert _xp(doc, "/*/cac:LegalMonetaryTotal/cbc:PayableAmount")[0].text == "100840.34"


def test_ubl_tax_inclusive_lines_are_netted_to_the_taxable_base() -> None:
    """Rotacion/salida lines are persisted at the tax-INCLUSIVE tariff price
    (200) while ``factura_impuestos`` holds base 168.07 + IVA 31.93. The UBL
    must not add the tax on top of the gross line: lines are netted to the
    taxable base so base + tax == the 200.00 charged."""
    from types import SimpleNamespace

    detalles = [
        SimpleNamespace(concepto="Parqueo", cantidad=1, valor_unitario=200.00, subtotal=200.00)
    ]
    impuestos = [
        SimpleNamespace(
            codigo="IVA", nombre="IVA", base_calculo=168.07,
            porcentaje_aplicado=0.19, valor=31.93,
        )
    ]
    xml_bytes = serialize(_build_factura_mock(), None, detalles=detalles, impuestos=impuestos)
    doc = etree.fromstring(xml_bytes)

    assert _xp(doc, "/*/cac:LegalMonetaryTotal/cbc:LineExtensionAmount")[0].text == "168.07"
    assert _xp(doc, "/*/cac:LegalMonetaryTotal/cbc:PayableAmount")[0].text == "200.00"
    assert _xp(doc, "/*/cac:TaxTotal/cbc:TaxAmount")[0].text == "31.93"
    line = _xp(doc, "/*/cac:InvoiceLine")[0]
    assert _xp(line, "cbc:LineExtensionAmount")[0].text == "168.07"
    assert _xp(line, "cac:Price/cbc:PriceAmount")[0].text == "168.07"
    assert _xp(line, "cac:TaxTotal/cbc:TaxAmount")[0].text == "31.93"
    schema = etree.XMLSchema(etree.parse(str(_XSD_MAIN_PATH)))
    assert schema.validate(doc), schema.error_log


def test_ubl_mensualidad_exit_with_full_discount_reconciles_to_zero() -> None:
    """Salida-mensualidad invoice: servicio (gross tariff 1500) + a
    'Descuento ...' line of the same value, charged total 0. The discount is
    a document-level allowance, never an InvoiceLine, so
    base 1260.50 + IVA 239.50 - descuento 1500.00 == payable 0.00."""
    from types import SimpleNamespace

    detalles = [
        SimpleNamespace(concepto="Parqueo", cantidad=1, valor_unitario=1500.00, subtotal=1500.00),
        SimpleNamespace(
            concepto="Descuento por mensualidad - Plan Mensual",
            cantidad=1, valor_unitario=1500.00, subtotal=1500.00,
        ),
    ]
    impuestos = [
        SimpleNamespace(
            codigo="IVA", nombre="IVA", base_calculo=1260.50,
            porcentaje_aplicado=0.19, valor=239.50,
        )
    ]
    xml_bytes = serialize(_build_factura_mock(), None, detalles=detalles, impuestos=impuestos)
    doc = etree.fromstring(xml_bytes)

    assert len(_xp(doc, "/*/cac:InvoiceLine")) == 1
    assert _xp(doc, "/*/cac:LegalMonetaryTotal/cbc:LineExtensionAmount")[0].text == "1260.50"
    assert _xp(doc, "/*/cac:TaxTotal/cbc:TaxAmount")[0].text == "239.50"
    assert _xp(doc, "/*/cac:LegalMonetaryTotal/cbc:TaxInclusiveAmount")[0].text == "1500.00"
    assert _xp(doc, "/*/cac:LegalMonetaryTotal/cbc:AllowanceTotalAmount")[0].text == "1500.00"
    assert _xp(doc, "/*/cac:LegalMonetaryTotal/cbc:PayableAmount")[0].text == "0.00"
    allowance = _xp(doc, "/*/cac:AllowanceCharge")
    assert len(allowance) == 1
    assert _xp(allowance[0], "cbc:ChargeIndicator")[0].text == "false"
    assert _xp(allowance[0], "cbc:Amount")[0].text == "1500.00"
    schema = etree.XMLSchema(etree.parse(str(_XSD_MAIN_PATH)))
    assert schema.validate(doc), schema.error_log


def _mensualidad_detalles(descuento: float) -> list:
    from types import SimpleNamespace

    return [
        SimpleNamespace(concepto="Parqueo", cantidad=1, valor_unitario=1500.00, subtotal=1500.00),
        SimpleNamespace(
            concepto="Descuento por mensualidad - Plan Mensual",
            cantidad=1, valor_unitario=descuento, subtotal=descuento,
        ),
    ]


def test_ubl_net_tax_full_discount_has_zero_tax_and_zero_payable() -> None:
    """AUD2: a salida-mensualidad invoice covered 100% by the subscription
    persists its IVA row on the NET taxable base (0 / 0). The UBL must not
    report a positive tax: line 1260.50 - allowance 1260.50 (both ex-IVA) =
    taxable 0, tax 0, payable 0."""
    from types import SimpleNamespace

    impuestos = [
        SimpleNamespace(
            codigo="IVA", nombre="IVA", base_calculo=0.00,
            porcentaje_aplicado=0.19, valor=0.00,
        )
    ]
    xml_bytes = serialize(
        _build_factura_mock(), None, detalles=_mensualidad_detalles(1500.00), impuestos=impuestos
    )
    doc = etree.fromstring(xml_bytes)

    assert _xp(doc, "/*/cac:TaxTotal/cbc:TaxAmount")[0].text == "0.00"
    assert _xp(doc, "/*/cac:TaxTotal/cac:TaxSubtotal/cbc:TaxableAmount")[0].text == "0.00"
    lm = "/*/cac:LegalMonetaryTotal/cbc:"
    assert _xp(doc, lm + "LineExtensionAmount")[0].text == "1260.50"
    assert _xp(doc, lm + "AllowanceTotalAmount")[0].text == "1260.50"
    assert _xp(doc, lm + "TaxExclusiveAmount")[0].text == "0.00"
    assert _xp(doc, lm + "TaxInclusiveAmount")[0].text == "0.00"
    assert _xp(doc, lm + "PayableAmount")[0].text == "0.00"
    assert _xp(doc, "/*/cac:AllowanceCharge/cbc:Amount")[0].text == "1260.50"
    line = _xp(doc, "/*/cac:InvoiceLine")[0]
    assert _xp(line, "cac:TaxTotal/cbc:TaxAmount")[0].text == "0.00"
    schema = etree.XMLSchema(etree.parse(str(_XSD_MAIN_PATH)))
    assert schema.validate(doc), schema.error_log


def test_ubl_net_tax_partial_discount_reconciles_to_the_net_total() -> None:
    """AUD2: total 1500 with a 500 discount -> net 1000 = base 840.34 + IVA 159.66.
    gross base 1260.50 - allowance(ex-IVA) 420.16 = 840.34; + tax = 1000.00."""
    from types import SimpleNamespace

    impuestos = [
        SimpleNamespace(
            codigo="IVA", nombre="IVA", base_calculo=840.34,
            porcentaje_aplicado=0.19, valor=159.66,
        )
    ]
    xml_bytes = serialize(
        _build_factura_mock(), None, detalles=_mensualidad_detalles(500.00), impuestos=impuestos
    )
    doc = etree.fromstring(xml_bytes)

    lm = "/*/cac:LegalMonetaryTotal/cbc:"
    assert _xp(doc, "/*/cac:TaxTotal/cbc:TaxAmount")[0].text == "159.66"
    assert _xp(doc, lm + "LineExtensionAmount")[0].text == "1260.50"
    assert _xp(doc, lm + "AllowanceTotalAmount")[0].text == "420.16"
    assert _xp(doc, lm + "TaxExclusiveAmount")[0].text == "840.34"
    assert _xp(doc, lm + "TaxInclusiveAmount")[0].text == "1000.00"
    assert _xp(doc, lm + "PayableAmount")[0].text == "1000.00"
    line_tax = _xp(doc, "/*/cac:InvoiceLine/cac:TaxTotal/cbc:TaxAmount")[0].text
    assert line_tax == "159.66"
    schema = etree.XMLSchema(etree.parse(str(_XSD_MAIN_PATH)))
    assert schema.validate(doc), schema.error_log
