"""
Audit-logging middleware.
Logs every request with user identity and response status.
Read-only mode — logs to console only, no DB writes.
"""

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("audit")


class AuditLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Try to extract user from the request state (set after auth)
        user = getattr(request.state, "user", None)
        username = user.get("sub") if user else "anonymous"
        client_ip = request.client.host if request.client else "-"

        logger.info(
            "method=%s  path=%s  status=%s  user=%s  ms=%.1f  ip=%s",
            request.method,
            request.url.path,
            response.status_code,
            username,
            elapsed_ms,
            client_ip,
        )

        return response
