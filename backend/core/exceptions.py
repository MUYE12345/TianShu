"""
自定义异常与全局异常处理器
"""
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse


class AppException(HTTPException):
    """应用基础异常"""
    def __init__(self, code: int, message: str, detail: str = ""):
        super().__init__(status_code=code, detail={
            "code": code,
            "message": message,
            "detail": detail,
        })


class NotFoundException(AppException):
    """资源不存在"""
    def __init__(self, resource: str, resource_id=None):
        rid = f"(id={resource_id})" if resource_id else ""
        super().__init__(404, f"{resource}不存在", f"{resource}{rid}未找到")


class BusinessException(AppException):
    """业务逻辑异常"""
    def __init__(self, message: str, detail: str = ""):
        super().__init__(400, message, detail)


class UnauthorizedException(AppException):
    """未授权"""
    def __init__(self, message: str = "请先登录"):
        super().__init__(401, message)


def register_exception_handlers(app: FastAPI):
    """注册全局异常处理器"""
    @app.exception_handler(AppException)
    async def app_exception_handler(request, exc: AppException):
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.status_code, "message": str(exc.detail)},
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request, exc: Exception):
        # 不对外回显异常详情(str(exc)), 避免泄露内部路径/密钥等; 详情写入日志
        import logging
        logging.getLogger(__name__).exception("未捕获异常: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"code": 500, "message": "服务器内部错误", "detail": ""},
        )
