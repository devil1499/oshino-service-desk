import argparse
import asyncio
import logging
from getpass import getpass

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import create_database_engine
from app.core.passwords import PasswordService
from app.core.settings import Settings
from app.models import TicketCategory, User
from app.modules.users.schemas import UserCreate, UserResponse

logger = logging.getLogger(__name__)
CATEGORIES = ("账号权限", "计费订阅", "功能使用", "配置集成", "性能故障", "服务不可用", "数据问题")


async def create_admin(settings: Settings, body: UserCreate) -> UserResponse:
    engine = create_database_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory.begin() as db:
            if await db.scalar(select(User.id).where(User.username == body.username)) is not None:
                raise ValueError("用户名已存在；初始化命令不会覆盖已有账号")
            user = User(
                username=body.username, display_name=body.display_name,
                password_hash=await PasswordService().hash(body.password), role="admin",
            )
            db.add(user)
            existing = set(await db.scalars(select(TicketCategory.name)))
            db.add_all(TicketCategory(name=name) for name in CATEGORIES if name not in existing)
            await db.flush()
            result = UserResponse.model_validate(user)
        return result
    finally:
        await engine.dispose()


def read_admin_input(username: str, display_name: str) -> UserCreate:
    password = getpass("管理员密码（8～128 位，不会显示）：")
    if password != getpass("再次输入密码："):
        raise ValueError("两次密码不一致")
    return UserCreate(username=username, display_name=display_name, password=password)


def main() -> None:
    parser = argparse.ArgumentParser(description="创建初始管理员并补齐默认分类")
    parser.add_argument("--username", required=True)
    parser.add_argument("--display-name", required=True)
    args = parser.parse_args()
    try:
        body = read_admin_input(args.username, args.display_name)
    except ValidationError as error:
        fields = "、".join(str(item["loc"][0]) for item in error.errors())
        raise SystemExit(f"管理员字段不符合规则：{fields}；请检查长度和用户名格式") from None
    except ValueError as error:
        raise SystemExit(str(error)) from None
    try:
        asyncio.run(create_admin(Settings.load(), body))
    except ValueError as error:
        raise SystemExit(str(error)) from None
    logger.info("管理员和默认分类已创建")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
