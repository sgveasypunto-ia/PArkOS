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
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from lxml import etree

# Module-level import guard (T-PR11-07 -- DIAN boundary layer 2).
# Kept as the first non-stdlib statement so branch deploys fail at
# module load, before any ORM import runs.
if os.environ.get("PARKOS_DEPLOY", "cloud").lower() == "branch":
    raise ImportError(
        "dian_cloud_unavailable_on_branch (T-PR11-07, REQ-X3, design section 10 Layer 2)"
    )

from ...constants import (
    CLIENTE_ESTANDAR_NOMBRE,
    CLIENTE_ESTANDAR_NUMERO_IDENTIFICACION,
    CLIENTE_ESTANDAR_TIPO_IDENTIFICADOR,
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

# Supplier placeholder. The customer is NOT a placeholder anymore: the FE
# always references a real ``prod.clientes`` row (the payer's, or the seeded
# standard customer "consumidor final", ``parkos_core.constants``); the
# caller passes it to :func:`serialize`. The minimal emission carries the
# customer identification + ``cac:PartyName``. PR12+ expands to the full DIAN
# party block (address, contact, tax scheme).
_SUPPLIER_NAME = "parkos"

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


def _customer_identity(cliente: Any | None) -> tuple[str, str, str]:
    """Return ``(tipo_identificador, numero_identificacion, nombre)``.

    ``cliente`` is a ``prod.clientes`` row (duck-typed). ``None`` -- or a row
    with no identification -- falls back to the standard customer.
    """
    numero = getattr(cliente, "numero_identificacion", None)
    if not numero:
        return (
            CLIENTE_ESTANDAR_TIPO_IDENTIFICADOR,
            CLIENTE_ESTANDAR_NUMERO_IDENTIFICACION,
            CLIENTE_ESTANDAR_NOMBRE,
        )
    tipo = getattr(cliente, "tipo_identificador", None) or CLIENTE_ESTANDAR_TIPO_IDENTIFICADOR
    partes = [getattr(cliente, "nombre", None), getattr(cliente, "apellido", None)]
    nombre = " ".join(p for p in partes if p) or CLIENTE_ESTANDAR_NOMBRE
    return str(tipo), str(numero), nombre


def _build_customer_party(cliente: Any | None) -> etree._Element:
    """Build ``cac:AccountingCustomerParty`` wrapping a ``cac:Party``."""
    tipo, numero, name = _customer_identity(cliente)
    customer = etree.Element(f"{{{NS_CAC}}}AccountingCustomerParty")
    customer_party = etree.SubElement(customer, f"{{{NS_CAC}}}Party")
    party_id = etree.SubElement(customer_party, f"{{{NS_CAC}}}PartyIdentification")
    id_el = etree.SubElement(party_id, f"{{{NS_CBC}}}ID")
    id_el.set("schemeName", tipo)
    id_el.text = numero
    party_name = etree.SubElement(customer_party, f"{{{NS_CAC}}}PartyName")
    name_el = etree.SubElement(party_name, f"{{{NS_CBC}}}Name")
    name_el.text = name
    return customer


_CENT = Decimal("0.01")

# DIAN tax-scheme codes (UBL ``cac:TaxScheme/cbc:ID``) by catalog ``codigo``.
_DIAN_TAX_SCHEME_ID = {"IVA": "01", "INC": "04", "ICA": "03"}


def _dec(value: Any) -> Decimal:
    """Coerce a Numeric/float/None to ``Decimal`` without float noise."""
    return Decimal(str(value if value is not None else 0))


def _q(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def _money_el(
    parent: etree._Element, tag: str, amount: Decimal | str, currency: str
) -> etree._Element:
    el = etree.SubElement(parent, f"{{{NS_CBC}}}{tag}")
    el.set("currencyID", currency)
    el.text = amount if isinstance(amount, str) else _format_money(amount)
    return el


def _build_tax_subtotal(
    *, taxable: Decimal, amount: Decimal, percent: Decimal, code: str, name: str, currency: str
) -> etree._Element:
    """Build ``cac:TaxSubtotal`` (base, amount, rate and tax scheme)."""
    sub = etree.Element(f"{{{NS_CAC}}}TaxSubtotal")
    _money_el(sub, "TaxableAmount", taxable, currency)
    _money_el(sub, "TaxAmount", amount, currency)
    category = etree.SubElement(sub, f"{{{NS_CAC}}}TaxCategory")
    etree.SubElement(category, f"{{{NS_CBC}}}Percent").text = f"{percent:.2f}"
    scheme = etree.SubElement(category, f"{{{NS_CAC}}}TaxScheme")
    etree.SubElement(scheme, f"{{{NS_CBC}}}ID").text = code
    etree.SubElement(scheme, f"{{{NS_CBC}}}Name").text = name
    return sub


def _build_tax_total(
    amount: str, currency: str, subtotals: list[etree._Element] | None = None
) -> etree._Element:
    """Build ``cac:TaxTotal``: ``TaxAmount`` + one ``TaxSubtotal`` per tax."""
    tax_total = etree.Element(f"{{{NS_CAC}}}TaxTotal")
    _money_el(tax_total, "TaxAmount", amount, currency)
    for sub in subtotals or []:
        tax_total.append(sub)
    return tax_total


def _build_legal_monetary_total(
    payable: str,
    currency: str,
    *,
    line_extension: str | None = None,
    tax_exclusive: str | None = None,
    tax_inclusive: str | None = None,
) -> etree._Element:
    """Build ``cac:LegalMonetaryTotal``.

    Without the optional amounts it emits the minimal stub (line extension
    == payable). With them: base (``LineExtensionAmount`` /
    ``TaxExclusiveAmount``), base + tax (``TaxInclusiveAmount``) and the
    ``PayableAmount``.
    """
    monetary = etree.Element(f"{{{NS_CAC}}}LegalMonetaryTotal")
    _money_el(monetary, "LineExtensionAmount", line_extension or payable, currency)
    if tax_exclusive is not None:
        _money_el(monetary, "TaxExclusiveAmount", tax_exclusive, currency)
    if tax_inclusive is not None:
        _money_el(monetary, "TaxInclusiveAmount", tax_inclusive, currency)
    _money_el(monetary, "PayableAmount", payable, currency)
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
    tax_total: etree._Element | None = None,
) -> etree._Element:
    """Build a ``cac:InvoiceLine`` block (with its own tax when given).

    UBL ``InvoiceLine`` requires ``ID`` + ``LineExtensionAmount`` +
    ``Item``; ``TaxTotal`` sits between the amount and the ``Item``.
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
    if tax_total is not None:
        inv_line.append(tax_total)

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


def _tax_identity(imp: Any) -> tuple[str, str, Decimal]:
    """``(scheme_id, name, percent)`` of a ``factura_impuestos`` row.

    ``porcentaje_aplicado`` is stored as a fraction (0.19) -> 19.00 %.
    """
    codigo = str(getattr(imp, "codigo", None) or "IVA")
    nombre = str(getattr(imp, "nombre", None) or codigo)
    percent = _q(_dec(getattr(imp, "porcentaje_aplicado", None)) * 100)
    return _DIAN_TAX_SCHEME_ID.get(codigo.upper(), codigo), nombre, percent


def _allocate_line_taxes(
    line_bases: list[Decimal], impuestos: list[Any]
) -> list[list[Decimal]]:
    """Split each document tax across the lines, pro rata to the line base.

    Returns ``allocation[line][tax]``; the LAST line absorbs the rounding so
    the per-line taxes of every tax add up exactly to its ``valor``.
    """
    total_base = sum(line_bases, Decimal(0))
    allocation: list[list[Decimal]] = [[] for _ in line_bases]
    for imp in impuestos:
        valor = _q(_dec(getattr(imp, "valor", None)))
        remaining = valor
        for idx, base in enumerate(line_bases):
            if idx == len(line_bases) - 1:
                share = remaining
            elif total_base == 0:
                share = Decimal(0)
            else:
                share = _q(valor * base / total_base)
            allocation[idx].append(share)
            remaining -= share
    return allocation


def _build_detailed_body(
    invoice: etree._Element, detalles: list[Any], impuestos: list[Any]
) -> None:
    """Append TaxTotal + LegalMonetaryTotal + InvoiceLines from persisted rows."""
    line_bases = [_q(_dec(d.subtotal)) for d in detalles]
    base_total = sum(line_bases, Decimal(0))
    tax_amounts = [_q(_dec(getattr(i, "valor", None))) for i in impuestos]
    tax_total = sum(tax_amounts, Decimal(0))
    identities = [_tax_identity(i) for i in impuestos]

    subtotals = [
        _build_tax_subtotal(
            taxable=_q(_dec(getattr(imp, "base_calculo", None))),
            amount=amount,
            percent=percent,
            code=scheme_id,
            name=name,
            currency=_CURRENCY_CODE,
        )
        for imp, amount, (scheme_id, name, percent) in zip(
            impuestos, tax_amounts, identities, strict=True
        )
    ]
    invoice.append(_build_tax_total(_format_money(tax_total), _CURRENCY_CODE, subtotals))
    invoice.append(
        _build_legal_monetary_total(
            _format_money(base_total + tax_total),
            _CURRENCY_CODE,
            line_extension=_format_money(base_total),
            tax_exclusive=_format_money(base_total),
            tax_inclusive=_format_money(base_total + tax_total),
        )
    )

    allocation = _allocate_line_taxes(line_bases, impuestos)
    for idx, det in enumerate(detalles):
        line_subtotals = [
            _build_tax_subtotal(
                taxable=line_bases[idx],
                amount=allocation[idx][t],
                percent=percent,
                code=scheme_id,
                name=name,
                currency=_CURRENCY_CODE,
            )
            for t, (scheme_id, name, percent) in enumerate(identities)
        ]
        line_tax = sum(allocation[idx], Decimal(0))
        invoice.append(
            _build_invoice_line(
                line_id=str(idx + 1),
                quantity=str(det.cantidad or 1),
                unit_code=_LINE_UNIT_CODE,
                line_amount=_format_money(line_bases[idx]),
                description=str(det.concepto or _LINE_DESCRIPTION),
                price_amount=_format_money(_dec(det.valor_unitario)),
                currency=_CURRENCY_CODE,
                tax_total=_build_tax_total(
                    _format_money(line_tax), _CURRENCY_CODE, line_subtotals
                ),
            )
        )


def serialize(
    factura: FacturaElectronica,
    cliente: Any | None = None,
    *,
    detalles: list[Any] | None = None,
    impuestos: list[Any] | None = None,
) -> bytes:
    """Build a UBL 2.1 XML payload from a ``factura_electronica`` row.

    Args:
        factura: The ``[L-E]`` row to serialize. Only header fields are
            read (``uuid``, ``prefijo``, ``consecutivo``, ``created_at``);
            the row is never mutated.
        cliente: The ``prod.clientes`` row referenced by
            ``factura.uuid_cliente`` (``None`` -> standard customer).
        detalles: ``prod.factura_detalle`` rows of the invoice. When given,
            one ``InvoiceLine`` per row and the totals come from the
            persisted rows (``None`` -> legacy zero-amount stub).
        impuestos: ``prod.factura_impuestos`` rows (duck-typed: ``codigo``,
            ``nombre``, ``base_calculo``, ``porcentaje_aplicado``, ``valor``).
            Emitted as ``TaxTotal/TaxSubtotal`` (base, rate, amount) and
            allocated to each line; base + tax == ``PayableAmount``.

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
    invoice.append(_build_customer_party(cliente))

    if detalles:
        _build_detailed_body(invoice, detalles, impuestos or [])
        return etree.tostring(
            invoice, xml_declaration=True, encoding="UTF-8", pretty_print=False
        )

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
