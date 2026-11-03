from fastapi.responses import JSONResponse

from app.llm import LLMError
from app.models import ErrorBody


def llm_error_response(e: LLMError) -> JSONResponse:
    body = ErrorBody(code=e.code, message=e.message, retryable=e.retryable)
    return JSONResponse(status_code=e.http_status, content={"error": body.model_dump()})
