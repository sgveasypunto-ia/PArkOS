"""DIAN cloud-only module (PR6, REQ-X3, design §10).

This package is **CLOUD-ONLY**:

- **Image-level** (design §10 Layer 1): the ``Dockerfile`` excludes
  ``parkos_core/dian/`` from branch images. Branch containers physically
  lack this directory.
- **Import-level** (design §10 Layer 2): :mod:`parkos_core.dian.cloud_router`
  has a top-level guard that raises :class:`ImportError` when
  ``PARKOS_DEPLOY=branch``. This is belt-and-suspenders — even if a
  branch image accidentally included the file, the guard prevents the
  cloud-only endpoints from loading.

See :mod:`parkos_core.dian.cloud_router` for the 4 cloud-only endpoints
(``POST /factura-electronica``, ``POST /envio-dian``,
``POST /validacion-evento``, ``POST /revocacion-factura-webhook``).
"""
