"""Generic client-facing errors for upstream generation failures: a fixed message, an error
code and a request id. The exception type and message are logged server-side under that
id; they never reach the client (and prompt content is never logged)."""
import logging
import uuid

from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

GENERATION_UNAVAILABLE = "generation_unavailable"


def generation_unavailable(exc: Exception, status_code: int, message: str) -> JSONResponse:
    request_id = uuid.uuid4().hex
    logger.error("Generation unavailable [request_id=%s]: %s: %s", request_id, type(exc).__name__, exc)
    return JSONResponse(
        status_code=status_code,
        content={
            "detail": f"{message} (reference {request_id})",
            "code": GENERATION_UNAVAILABLE,
            "request_id": request_id,
        },
    )
