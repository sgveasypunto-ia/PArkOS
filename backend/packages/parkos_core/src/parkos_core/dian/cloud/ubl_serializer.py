"""UBL 2.1 XML serializer for ``factura_electronica`` rows (T-PR11-03 + PR11c).

Full UBL 2.1 emission using ``lxml`` for namespace-correct element
construction. The output validates against the bundled XSD at
``parkos_core/dian/cloud/xsd/maindoc/UBL-Invoice-2.1.xsd`` (T-PR11-13
acceptance gate -- see ``tests/unit/dian/test_ubl_serializer.py``).

The serializer reads ONLY the ``FacturaElectronica`` row header fields
(``uuid``, ``prefijo``, ``consecutivo``, ``created_at``). Lines, taxes,
and totals live on the related ``facturas`` / ``factura_detalle`` rows
and are resolved by the cloud router before reaching this serializer;
this PR's scope keeps the line/total emission at the minimum XSD
requirement (one InvoiceLine + zero TaxTotal + zero payable amount) --
subsequent PRs expand the line iteration as the factura-detalle
plumbing lands.

Issuer: cloud-only (module-level import guard below).
"""
from __future__ import annotations

import os
from datetime import UTC, datetime
from decimal import Decimal

from lxml import etree

# Module-level import guard (T-PR11-07 -- DIAN boundary layer 2).
# Kept as the first non-stdlib statement so branch deploys fail at
# module load, before any ORM import runs.
if os.environ.get("PARKOS_DEPLOY", "cloud").lower() == "branch":
    raise ImportError(
        "dian_cloud_unavailable_on_branch (T-PR11-07, REQ-X3, design section 10 Layer 2)"
    )

from ...models.L_E.factura_electronica import FacturaElectronica

# UBL 2.1 namespaces (OASIS canonical URIs).
NS_INVOICE = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
NS_CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
NS_CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
NSMAP = {
    None: NS_INVOICE,
    "cac": NS_CAC,
    "cbc": NS_CBC,
}

# Fallback prefix when the resolution carries none. DIAN's sandbox
# prefix; a production row always resolves ``prefijo`` from
# ``resolucion_facturacion`` before reaching this serializer.
_DEFAULT_PREFIJO = "SETP"

# DIAN ``InvoiceTypeCode`` for a "factura de venta" -- the only type the
# resolution range currently authorises (REQ-OP-12).
_DIAN_INVOICE_TYPE_CODE = "01"

_CURRENCY_CODE = "COP"

# Supplier / customer placeholders. The cloud router resolves the real
# party data from ``prod.empresa`` and ``prod.clientes`` before this
# serializer is called; the PR11c minimal emission carries only the
# XSD-required ``cac:PartyName/cbc:Name`` child. PR12+ expands to the
# full DIAN party block (NIT, address, contact, tax scheme).
_SUPPLIER_NAME = "parkos"
_CUSTOMER_NAME = "consumidor_final"

# Line / total placeholders. Same scope story as the parties: the line
# iteration lands with the ``factura_detalle`` router work (PR12).
_LINE_ID = "1"
_LINE_DESCRIPTION = "servicio de parqueo"
_LINE_QUANTITY = "1"
_LINE_UNIT_CODE = "UN"
_LINE_AMOUNT = "0.00"
_TAX_AMOUNT = "0.00"
_PAYABLE_AMOUNT = "0.00"


def _now_naive() -> datetime:
    """Naive UTC ``datetime`` -- matches ``repo/versioned.py`` style."""
    return datetime.now(UTC).replace(tzinfo=None)


def _format_money(amount: Decimal | float | str) -> str:
    """Render a money value with two decimal places (UBL canonical form)."""
    return f"{Decimal(str(amount)):.2f}"


def _build_supplier_party(name: str) -> etree._Element:
    """Build ``cac:AccountingSupplierParty`` wrapping a ``cac:Party``.

    The UBL XSD requires ``PartyName`` (minOccurs=1, maxOccurs=1 within
    Party). The cloud router will replace this minimal stub with the
    full NIT + address + tax-scheme block once ``prod.empresa``
    resolution lands (PR12).
    """
    supplier = etree.Element(f"{{{NS_CAC}}}AccountingSupplierParty")
    supplier_party = etree.SubElement(supplier, f"{{{NS_CAC}}}Party")
    party_name = etree.SubElement(supplier_party, f"{{{NS_CAC}}}PartyName")
    name_el = etree.SubElement(party_name, f"{{{NS_CBC}}}Name")
    name_el.text = name
    return supplier


def _build_customer_party(name: str) -> etree._Element:
    """Build ``cac:AccountingCustomerParty`` wrapping a ``cac:Party``."""
    customer = etree.Element(f"{{{NS_CAC}}}AccountingCustomerParty")
    customer_party = etree.SubElement(customer, f"{{{NS_CAC}}}Party")
    party_name = etree.SubElement(customer_party, f"{{{NS_CAC}}}PartyName")
    name_el = etree.SubElement(party_name, f"{{{NS_CBC}}}Name")
    name_el.text = name
    return customer


def _build_tax_total(amount: str, currency: str) -> etree._Element:
    """Build ``cac:TaxTotal`` with the required ``TaxAmount`` + currency.

    UBL ``TaxAmount`` carries an optional ``currencyID`` attribute; the
    XSD binds it to ``Currency_ Code. Type``. ``cac:TaxTotal`` itself
    appears minOccurs=0 on InvoiceType, so emitting one with ``0.00``
    is the safe minimal stub for PR11c -- PR12+ reads the real
    ``factura_impuestos`` rows and emits one ``TaxTotal`` per active
    tax code.
    """
    tax_total = etree.Element(f"{{{NS_CAC}}}TaxTotal")
    tax_amount = etree.SubElement(tax_total, f"{{{NS_CBC}}}TaxAmount")
    tax_amount.set("currencyID", currency)
    tax_amount.text = amount
    return tax_total


def _build_legal_monetary_total(payable: str, currency: str) -> etree._Element:
    """Build ``cac:LegalMonetaryTotal`` with the required ``PayableAmount``.

    ``LegalMonetaryTotal`` carries ``PayableAmount`` (minOccurs=1) +
    ``LineExtensionAmount`` (minOccurs=1). PR12 reads the real totals
    from ``factura_detalle`` + ``factura_impuestos`` + ``factura_otros_cobros``;
    this stub emits the minimum XSD-valid block with zero amounts.
    """
    monetary = etree.Element(f"{{{NS_CAC}}}LegalMonetaryTotal")
    line_ext = etree.SubElement(monetary, f"{{{NS_CBC}}}LineExtensionAmount")
    line_ext.set("currencyID", currency)
    line_ext.text = payable
    payable_el = etree.SubElement(monetary, f"{{{NS_CBC}}}PayableAmount")
    payable_el.set("currencyID", currency)
    payable_el.text = payable
    return monetary


def _build_invoice_line(
    *,
    line_id: str,
    quantity: str,
    unit_code: str,
    line_amount: str,
    description: str,
    price_amount: str,
    currency: str,
) -> etree._Element:
    """Build a minimal ``cac:InvoiceLine`` block.

    UBL ``InvoiceLine`` requires ``ID`` + ``LineExtensionAmount`` +
    ``Item``. ``Item`` itself requires at least one name child. We
    emit ``cbc:Description`` (allowed on Item, no minOccurs) plus the
    required name via ``cbc:Name``. ``Price`` requires
    ``PriceAmount`` (minOccurs=1).
    """
    inv_line = etree.Element(f"{{{NS_CAC}}}InvoiceLine")
    id_el = etree.SubElement(inv_line, f"{{{NS_CBC}}}ID")
    id_el.text = line_id
    qty_el = etree.SubElement(inv_line, f"{{{NS_CBC}}}InvoicedQuantity")
    qty_el.set("unitCode", unit_code)
    qty_el.text = quantity
    line_ext = etree.SubElement(inv_line, f"{{{NS_CBC}}}LineExtensionAmount")
    line_ext.set("currencyID", currency)
    line_ext.text = line_amount

    item = etree.SubElement(inv_line, f"{{{NS_CAC}}}Item")
    desc_el = etree.SubElement(item, f"{{{NS_CBC}}}Description")
    desc_el.text = description
    name_el = etree.SubElement(item, f"{{{NS_CBC}}}Name")
    name_el.text = description

    price = etree.SubElement(inv_line, f"{{{NS_CAC}}}Price")
    price_amount_el = etree.SubElement(price, f"{{{NS_CBC}}}PriceAmount")
    price_amount_el.set("currencyID", currency)
    price_amount_el.text = price_amount
    return inv_line


def serialize(factura: FacturaElectronica) -> bytes:
    """Build a UBL 2.1 XML payload from a ``factura_electronica`` row.

    Args:
        factura: The ``[L-E]`` row to serialize. Only header fields are
            read (``uuid``, ``prefijo``, ``consecutivo``, ``created_at``);
            the row is never mutated.

    Returns:
        UTF-8 encoded XML bytes, ready to POST to the DIAN provider.
        The output validates against the bundled
        ``UBL-Invoice-2.1.xsd`` (T-PR11-13 acceptance gate).
    """
    now = _now_naive()
    created_at = factura.created_at or now
    issue_date = created_at.date().isoformat()
    issue_time = created_at.time().isoformat(timespec="seconds")
    consecutivo = factura.consecutivo or 0
    prefijo = factura.prefijo or _DEFAULT_PREFIJO
    doc_number = f"{prefijo}{consecutivo}"
    doc_uuid = str(factura.uuid)

    # --- Build the Invoice document ---
    invoice = etree.Element(f"{{{NS_INVOICE}}}Invoice", nsmap=NSMAP)

    # Header (minOccurs=1 for ID + IssueDate; the rest are canonical).
    ubl_version = etree.SubElement(invoice, f"{{{NS_CBC}}}UBLVersionID")
    ubl_version.text = "2.1"
    customization = etree.SubElement(invoice, f"{{{NS_CBC}}}CustomizationID")
    customization.text = "parkos-1.0"
    doc_id = etree.SubElement(invoice, f"{{{NS_CBC}}}ID")
    doc_id.text = doc_number
    uuid_el = etree.SubElement(invoice, f"{{{NS_CBC}}}UUID")
    uuid_el.text = doc_uuid
    issue_date_el = etree.SubElement(invoice, f"{{{NS_CBC}}}IssueDate")
    issue_date_el.text = issue_date
    issue_time_el = etree.SubElement(invoice, f"{{{NS_CBC}}}IssueTime")
    issue_time_el.text = issue_time
    invoice_type_code = etree.SubElement(invoice, f"{{{NS_CBC}}}InvoiceTypeCode")
    invoice_type_code.text = _DIAN_INVOICE_TYPE_CODE
    currency_el = etree.SubElement(invoice, f"{{{NS_CBC}}}DocumentCurrencyCode")
    currency_el.text = _CURRENCY_CODE

    # Parties (both minOccurs=1).
    invoice.append(_build_supplier_party(_SUPPLIER_NAME))
    invoice.append(_build_customer_party(_CUSTOMER_NAME))

    # Totals (minOccurs=1 for LegalMonetaryTotal; TaxTotal optional).
    invoice.append(_build_tax_total(_TAX_AMOUNT, _CURRENCY_CODE))
    invoice.append(_build_legal_monetary_total(_PAYABLE_AMOUNT, _CURRENCY_CODE))

    # At least one InvoiceLine (minOccurs=1, unbounded). PR12 expands to
    # N lines per the related ``factura_detalle`` rows.
    invoice.append(
        _build_invoice_line(
            line_id=_LINE_ID,
            quantity=_LINE_QUANTITY,
            unit_code=_LINE_UNIT_CODE,
            line_amount=_LINE_AMOUNT,
            description=_LINE_DESCRIPTION,
            price_amount=_LINE_AMOUNT,
            currency=_CURRENCY_CODE,
        )
    )

    return etree.tostring(
        invoice,
        xml_declaration=True,
        encoding="UTF-8",
        pretty_print=False,
    )


__all__ = ["serialize"]
