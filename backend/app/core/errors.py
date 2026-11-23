import logging
from collections.abc import Mapping
from typing import cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException

logger = logging.getLogger(__name__)


class ValidationIssue(BaseModel):
    loc: list[str | int]
    msg: str


class ErrorResponse(BaseModel):
    code: str
    message: str
    request_id: str
    detail: str | list[ValidationIssue]


def error_response(
    request: Request,
    status: int,
    message: str,
    detail: list[ValidationIssue] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    identifier = cast(str, request.state.request_id)
    body = ErrorResponse(
        code=f"HTTP_{status}", message=message, request_id=identifier,
        detail=detail if detail is not None else message,
    )
    return JSONResponse(
        status_code=status, content=body.model_dump(), headers={**(headers or {}), "X-Request-ID": identifier}
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException) -> JSONResponse:
        return error_response(request, error.status_code, str(error.detail), headers=error.headers)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
        translations = {
            "missing": "此字段必填", "extra_forbidden": "不允许提供此字段",
            "string_too_short": "长度不足", "string_too_long": "长度超过上限",
            "string_pattern_mismatch": "格式不正确", "greater_than": "必须大于允许的最小值",
            "greater_than_equal": "低于允许的最小值", "less_than_equal": "超过允许的最大值",
        }
        issues = [
            ValidationIssue(loc=list(item["loc"]), msg=translations.get(item["type"], "字段类型或取值不正确"))
            for item in error.errors()
        ]
        return error_response(request, 422, "请求参数不正确", issues)

    @app.exception_handler(IntegrityError)
    async def integrity_error(request: Request, error: IntegrityError) -> JSONResponse:
        if getattr(error.orig, "sqlstate", None) == "23505":
            return error_response(request, 409, "名称或用户名已存在")
        logger.error("数据库约束检查失败，request_id=%s", request.state.request_id, exc_info=True)
        return error_response(request, 500, "数据保存失败，请联系管理员")

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, error: SQLAlchemyError) -> JSONResponse:
        logger.error("数据库访问失败，request_id=%s", request.state.request_id, exc_info=True)
        return error_response(request, 503, "数据库暂时不可用，请稍后重试")

    @app.exception_handler(TimeoutError)
    async def timed_out(request: Request, error: TimeoutError) -> JSONResponse:
        return error_response(request, 503, "处理超时，请稍后重试")

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, error: Exception) -> JSONResponse:
        logger.error("请求处理失败，request_id=%s", request.state.request_id, exc_info=True)
        return error_response(request, 500, "服务器处理失败，请联系管理员")
