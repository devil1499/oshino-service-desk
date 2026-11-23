from datetime import UTC, datetime, timedelta
from typing import Annotated, cast

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.passwords import PasswordService
from app.core.settings import Settings
from app.models import User

bearer = HTTPBearer(auto_error=False)
# Annotated 标注类型，Depends 告诉 FastAPI 从 get_db 获取本次请求的数据库会话。
DbSession = Annotated[AsyncSession, Depends(get_db)]


def get_settings(request: Request) -> Settings:
    # 启动时已把 Settings 放入 app.state；cast 仅帮助类型检查，不转换或校验数据。
    return cast(Settings, request.app.state.settings)


def get_passwords(request: Request) -> PasswordService:
    return cast(PasswordService, request.app.state.passwords)


AppSettings = Annotated[Settings, Depends(get_settings)]
Passwords = Annotated[PasswordService, Depends(get_passwords)]


def create_access_token(user_id: int, settings: Settings) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {"sub": str(user_id), "iat": now, "exp": now + timedelta(minutes=settings.access_token_minutes)},
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )


async def get_current_user(
    db: DbSession,
    settings: AppSettings,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    unauthorized = HTTPException(
        status_code=401, detail="请登录或重新登录", headers={"WWW-Authenticate": "Bearer"}
    )
    if credentials is None:
        raise unauthorized
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            options={"require": ["sub", "iat", "exp"]},
        )
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, ValueError, TypeError) as error:
        raise unauthorized from error
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized
    return user


AuthenticatedUser = Annotated[User, Depends(get_current_user)]


def require_staff(user: AuthenticatedUser) -> User:
    if user.role not in {"admin", "staff"}:
        raise HTTPException(status_code=403, detail="此入口仅供客服使用")
    return user


CurrentUser = Annotated[User, Depends(require_staff)]


def require_admin(user: CurrentUser) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="此操作需要管理员权限")
    return user


AdminUser = Annotated[User, Depends(require_admin)]
