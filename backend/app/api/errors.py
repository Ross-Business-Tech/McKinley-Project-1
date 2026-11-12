import logging

from fastapi.responses import JSONResponse

from app.llm import LLMError
from app.models import ErrorBody


def http_error_response(status_code: int, detail: object, headers: dict[str, str] | None = None) -> JSONResponse:
    """One error envelope for the whole API: {"error": {code, message, retryable}}. A structured detail keeps its
    code; a plain string detail gets HTTP_<status>. (422 request-validation errors keep FastAPI's own shape.)"""
    if isinstance(detail, dict) and isinstance(detail.get("code"), str):
        body = ErrorBody(code=detail["code"], message=str(detail.get("message") or ""),
                         retryable=bool(detail.get("retryable", False)))
    else:
        body = ErrorBody(code=f"HTTP_{status_code}", message=str(detail or ""), retryable=status_code >= 500)
    return JSONResponse(status_code=status_code, content={"error": body.model_dump()}, headers=headers)


def llm_error_response(e: LLMError) -> JSONResponse:
    body = ErrorBody(code=e.code, message=e.message, retryable=e.retryable)
    return JSONResponse(status_code=e.http_status, content={"error": body.model_dump()})


log = logging.getLogger("mckinley.api")

# Model problems a customer can wait out (busy, slow, briefly unreachable) vs a deployment problem (no key, a key the
# provider rejects, a model that does not exist) that only the team can fix. Customers never see the provider's own
# message: it can name configuration files, environment variables or the provider's address.
TEMPORARY_LLM_CODES = {"MODEL_RATE_LIMITED", "MODEL_TIMEOUT", "MODEL_CONNECTION_ERROR", "MODEL_API_ERROR",
                       "MODEL_EMPTY_RESPONSE", "MODEL_BAD_RESPONSE", "MODEL_TRUNCATED", "MODEL_REFUSAL",
                       "LLM_BUDGET_EXHAUSTED"}
ASSISTANT_BUSY = ("ASSISTANT_BUSY", "The assistant is busy right now. Please try again in a moment.")
ASSISTANT_UNAVAILABLE = ("ASSISTANT_UNAVAILABLE", "The assistant is not available right now. Please contact the "
                                                  "office directly.")


def customer_llm_error_response(e: LLMError) -> JSONResponse:
    """The customer-safe version of an LLM error: a fixed message, the original code only in the server log."""
    temporary = e.code in TEMPORARY_LLM_CODES or e.retryable
    code, message = ASSISTANT_BUSY if temporary else ASSISTANT_UNAVAILABLE
    log.warning("chat turn failed: %s (customer sees %s)", e.code, code)
    body = ErrorBody(code=code, message=message, retryable=temporary)
    return JSONResponse(status_code=503, content={"error": body.model_dump()})
