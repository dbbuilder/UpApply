"""Generic client-facing errors for upstream generation failures: a fixed message, an error
code and a request id. Only the exception type and, for LLMError, its fixed reason category
are logged under that id: exception messages can carry prompt/upstream text, so they are
never logged or returned."""
import logging
import uuid

from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

GENERATION_UNAVAILABLE = "generation_unavailable"


def generation_unavailable(exc: Exception, status_code: int, message: str) -> JSONResponse:
    request_id = uuid.uuid4().hex
    logger.error("Generation unavailable [request_id=%s]: %s reason=%s",
                 request_id, type(exc).__name__, getattr(exc, "reason", "-"))
    return JSONResponse(
        status_code=status_code,
        content={
            "detail": f"{message} (reference {request_id})",
            "code": GENERATION_UNAVAILABLE,
            "request_id": request_id,
        },
    )
