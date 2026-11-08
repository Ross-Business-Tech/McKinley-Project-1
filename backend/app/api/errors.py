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
