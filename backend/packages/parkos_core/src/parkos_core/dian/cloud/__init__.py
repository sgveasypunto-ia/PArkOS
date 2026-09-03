"""DIAN cloud-only dispatcher package (PR11).

This package exists ONLY on cloud deploys. The boundary is enforced at
three layers (REQ-X3, design §10):

1. **Image level** — ``backend/.dockerignore`` excludes
   ``**/dian/cloud/**`` from branch images, so the modules are not even
   present on disk (``ModuleNotFoundError``).
2. **Import level** — every module in this package carries a
   module-level ``PARKOS_DEPLOY`` guard that raises
   ``ImportError("dian_cloud_unavailable_on_branch")``.
3. **OpenAPI level** — the cloud-only tag filter keeps the DIAN paths
   out of ``api_sucursal/openapi.json``.

This ``__init__`` intentionally carries NO guard: the guard belongs on
the modules that hold DIAN behaviour, so a branch-side ``import
parkos_core.dian.cloud`` for introspection does not explode while any
attempt to reach the dispatcher, the serializer, or a provider adapter
does.
"""
from __future__ import annotations
