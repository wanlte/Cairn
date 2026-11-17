from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from apps.api.logging import request_id_var


class AppError(Exception):
    def __init__(
        self, code: str, message: str, status_code: int = 400, retryable: bool = False
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        super().__init__(message)


def _body(code: str, message: str, retryable: bool) -> dict:
    return {
        "code": code,
        "message": message,
        "request_id": request_id_var.get(),
        "retryable": retryable,
    }


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_body(exc.code, exc.message, exc.retryable),
        )
