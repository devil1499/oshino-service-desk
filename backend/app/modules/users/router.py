from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.core.pagination import Page, PageSize
from app.core.security import (
    AdminUser, AppSettings, AuthenticatedUser, CurrentUser, DbSession, Passwords, create_access_token,
)
from app.models import User
from app.modules.users.schemas import LoginRequest, LoginResponse, UserCreate, UserResponse, UserState

router = APIRouter(prefix="/api", tags=["用户"])


@router.post("/auth/login", response_model=LoginResponse)
async def login(body: LoginRequest, db: DbSession, settings: AppSettings, passwords: Passwords) -> LoginResponse:
    user = await db.scalar(select(User).where(User.username == body.username))
    if user is None or not await passwords.verify(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账号已停用")
    return LoginResponse(access_token=create_access_token(user.id, settings), user=UserResponse.model_validate(user))


@router.get("/auth/me", response_model=UserResponse)
async def me(user: AuthenticatedUser) -> UserResponse:
    return UserResponse.model_validate(user)


@router.get("/users", response_model=list[UserResponse])
async def list_users(db: DbSession, user: CurrentUser, page: Page = 1, page_size: PageSize = 100) -> list[UserResponse]:
    users = await db.scalars(
        select(User).where(User.role.in_(["admin", "staff"]))
        .order_by(User.id).offset((page - 1) * page_size).limit(page_size)
    )
    return [UserResponse.model_validate(item) for item in users]


@router.post("/users", response_model=UserResponse, status_code=201)
async def create_staff(body: UserCreate, db: DbSession, admin: AdminUser, passwords: Passwords) -> UserResponse:
    user = User(
        username=body.username,
        display_name=body.display_name,
        password_hash=await passwords.hash(body.password),
        role="staff",
    )
    db.add(user)
    await db.commit()
    return UserResponse.model_validate(user)


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_staff_state(user_id: int, body: UserState, db: DbSession, admin: AdminUser) -> UserResponse:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.role == "admin":
        raise HTTPException(status_code=409, detail="本接口只管理客服账号")
    user.is_active = body.is_active
    await db.commit()
    return UserResponse.model_validate(user)
