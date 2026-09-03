"""HTTP middlewares (REQ-OP-04 + design §8).

PR1b ships:
- :class:`IdempotencyKeyMiddleware` — extracts ``Idempotency-Key`` and stashes
  it on ``request.state.idempotency_key``. Does NOT enforce presence — the
  per-route helper does, so GET endpoints and OPTIONS preflights are unaffected.

PR7 ships the actual idempotency_keys table + per-route guard. Until then
the middleware is a no-op stub that just plumbs the header through.
"""
from __future__ import annotations

import logging

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class IdempotencyKeyMiddleware(BaseHTTPMiddleware):
    """Stash the ``Idempotency-Key`` header on ``request.state`` for
    downstream handlers.

    Per design §8: this middleware is intentionally minimal — it does NOT
    enforce header presence (the per-route helper does, so that GET
    endpoints and OPTIONS preflights are unaffected).
    """

    async def dispatch(self, request: Request, call_next):
        request.state.idempotency_key = request.headers.get("Idempotency-Key")
        if request.state.idempotency_key:
            logger.debug(
                "idempotency_key_seen",
                extra={
                    "path": request.url.path,
                    "method": request.method,
                },
            )
        return await call_next(request)


__all__ = ["IdempotencyKeyMiddleware"]