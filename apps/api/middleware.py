import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from apps.api.logging import get_logger, request_id_var

logger = get_logger()


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = request_id_var.set(rid)
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = rid
            return response
        except Exception as exc:
            logger.error(
                "request_failed",
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                error_type=type(exc).__name__,
            )
            raise
        finally:
            latency_ms = int((time.perf_counter() - started) * 1000)
            logger.info(
                "http_request",
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                latency_ms=latency_ms,
            )
            request_id_var.reset(token)
