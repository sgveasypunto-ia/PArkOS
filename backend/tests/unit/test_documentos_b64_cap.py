"""Schema-only tests for ``prod.documentos`` 1MB base64 cap (REQ-OP-05).

The ``documento_b64`` field carries a base64-encoded binary document. The
DIAN contract caps documents at 1MB, encoded as base64 = 1_400_000 chars
(ceil(1_048_576 / 3) * 4 ~= 1_398_101, rounded up with safety margin).

Per the PR3 plan, this PR ships schema-only tests (no DB). Integration
tests against a real Postgres land in a later PR once testcontainers is
wired in CI.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime

import pytest
from parkos_core.schemas.empresa import (
    DocumentosCreate,
    DocumentosRead,
    DocumentosReadList,
    DocumentosUpdate,
)
from pydantic import ValidationError

SUCURSAL_UUID = uuid_lib.UUID("00000000-0000-0000-0000-00000000000d")
NOW = datetime(2026, 1, 1)
B64_MAX = 1_400_000


class TestDocumentosB64Cap:
    """``documento_b64`` MUST be <= 1_400_000 chars (1MB base64 cap, REQ-OP-05)."""

    def test_accepts_exactly_max_length(self):
        """Exactly 1_400_000 chars -> accepted (boundary inclusive)."""
        b64 = "A" * B64_MAX
        c = DocumentosCreate(
            uuid_sucursal=SUCURSAL_UUID,
            tipo="contrato",
            formato="pdf",
            documento_b64=b64,
        )
        assert len(c.documento_b64) == B64_MAX

    @pytest.mark.parametrize("overshoot", [1, 100, B64_MAX - 100, 1_000_000])
    def test_rejects_above_max_length(self, overshoot):
        """``B64_MAX + overshoot`` chars -> rejected with ValidationError."""
        b64 = "A" * (B64_MAX + overshoot)
        with pytest.raises(ValidationError) as exc_info:
            DocumentosCreate(
                uuid_sucursal=SUCURSAL_UUID,
                tipo="contrato",
                formato="pdf",
                documento_b64=b64,
            )
        assert "documento_b64" in str(exc_info.value)

    def test_accepts_typical_base64(self):
        """Realistic 1KB base64 string -> accepted."""
        # 1024 chars of plausible base64 alphabet.
        b64 = (
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
            * 16  # 64 * 16 = 1024 chars
        )
        c = DocumentosCreate(
            uuid_sucursal=SUCURSAL_UUID,
            tipo="contrato",
            formato="pdf",
            documento_b64=b64,
        )
        assert len(c.documento_b64) == 1024

    @pytest.mark.parametrize("overshoot", [1, 100, B64_MAX - 100, 1_000_000])
    def test_update_rejects_above_max_length(self, overshoot):
        """Same cap applies to ``DocumentosUpdate``."""
        b64 = "A" * (B64_MAX + overshoot)
        with pytest.raises(ValidationError) as exc_info:
            DocumentosUpdate(
                uuid_sucursal=SUCURSAL_UUID,
                tipo="contrato",
                formato="pdf",
                documento_b64=b64,
            )
        assert "documento_b64" in str(exc_info.value)


class TestDocumentosRequiredFields:
    """``uuid_sucursal`` and ``tipo`` and ``documento_b64`` are required on Create."""

    def test_create_missing_uuid_sucursal(self):
        with pytest.raises(ValidationError):
            DocumentosCreate(
                tipo="contrato",
                formato="pdf",
                documento_b64="AAA",
            )

    def test_create_missing_tipo(self):
        with pytest.raises(ValidationError):
            DocumentosCreate(
                uuid_sucursal=SUCURSAL_UUID,
                formato="pdf",
                documento_b64="AAA",
            )

    def test_create_missing_documento_b64(self):
        """``documento_b64`` has no default -> required."""
        with pytest.raises(ValidationError):
            DocumentosCreate(
                uuid_sucursal=SUCURSAL_UUID,
                tipo="contrato",
                formato="pdf",
            )

    def test_create_formato_optional(self):
        """``formato`` is optional (defaults to None)."""
        c = DocumentosCreate(
            uuid_sucursal=SUCURSAL_UUID,
            tipo="contrato",
            documento_b64="AAA",
        )
        assert c.formato is None

    def test_create_accepts_max_formato(self):
        """``formato`` max length is 32 chars."""
        c = DocumentosCreate(
            uuid_sucursal=SUCURSAL_UUID,
            tipo="contrato",
            formato="x" * 32,
            documento_b64="AAA",
        )
        assert len(c.formato) == 32

    def test_create_rejects_overlong_formato(self):
        """``formato`` beyond 32 chars -> ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            DocumentosCreate(
                uuid_sucursal=SUCURSAL_UUID,
                tipo="contrato",
                formato="x" * 33,
                documento_b64="AAA",
            )
        assert "formato" in str(exc_info.value)

    @pytest.mark.parametrize(
        "forbidden", ["vigente_desde", "vigente_hasta", "estado", "uuid", "created_at"]
    )
    def test_create_excludes_versioning_columns(self, forbidden):
        """``Create`` MUST reject versioning/system columns (``extra='forbid'``)."""
        with pytest.raises(ValidationError):
            DocumentosCreate(
                uuid_sucursal=SUCURSAL_UUID,
                tipo="contrato",
                documento_b64="AAA",
                **{forbidden: NOW},
            )


class TestTipoLength:
    """``tipo`` MUST be 1-64 chars."""

    @pytest.mark.parametrize("bad", ["", "x" * 65])
    def test_create_rejects_bad_tipo(self, bad):
        with pytest.raises(ValidationError):
            DocumentosCreate(
                uuid_sucursal=SUCURSAL_UUID,
                tipo=bad,
                documento_b64="AAA",
            )

    def test_create_accepts_max_tipo(self):
        c = DocumentosCreate(
            uuid_sucursal=SUCURSAL_UUID,
            tipo="x" * 64,
            documento_b64="AAA",
        )
        assert len(c.tipo) == 64

    def test_create_accepts_min_tipo(self):
        c = DocumentosCreate(
            uuid_sucursal=SUCURSAL_UUID,
            tipo="x",
            documento_b64="AAA",
        )
        assert len(c.tipo) == 1


class TestReadMirrorsORM:
    """``DocumentosRead`` includes ``documento_b64`` (returned from ORM)."""

    def test_read_includes_b64(self):
        b64 = "x" * 1000
        r = DocumentosRead(
            uuid=uuid_lib.UUID("00000000-0000-0000-0000-000000000099"),
            uuid_sucursal=SUCURSAL_UUID,
            tipo="contrato",
            formato="pdf",
            documento_b64=b64,
            vigente_desde=NOW,
            vigente_hasta=None,
            estado="activo",
            created_at=NOW,
            created_by=None,
            sync_status=None,
        )
        assert r.documento_b64 == b64
        assert r.uuid_sucursal == SUCURSAL_UUID

    def test_read_b64_optional(self):
        """``DocumentosRead.documento_b64`` is Optional (matches ORM nullable)."""
        r = DocumentosRead(
            uuid=uuid_lib.UUID("00000000-0000-0000-0000-00000000009b"),
            uuid_sucursal=SUCURSAL_UUID,
            tipo="contrato",
            formato="pdf",
            documento_b64=None,
            vigente_desde=NOW,
            vigente_hasta=None,
            estado="activo",
            created_at=NOW,
            created_by=None,
            sync_status=None,
        )
        assert r.documento_b64 is None


class TestReadListShape:
    """``DocumentosReadList`` is a cursor-paginated list."""

    def test_empty_list(self):
        rl = DocumentosReadList(items=[], next_cursor=None)
        assert rl.items == []
        assert rl.next_cursor is None

    def test_with_cursor(self):
        r = DocumentosRead(
            uuid=uuid_lib.UUID("00000000-0000-0000-0000-00000000009a"),
            uuid_sucursal=SUCURSAL_UUID,
            tipo="recibo",
            formato="pdf",
            documento_b64="x" * 100,
            vigente_desde=NOW,
            vigente_hasta=None,
            estado="activo",
            created_at=NOW,
            created_by=None,
            sync_status=None,
        )
        rl = DocumentosReadList(items=[r], next_cursor="abc")
        assert len(rl.items) == 1
        assert rl.next_cursor == "abc"
