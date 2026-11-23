import argparse
import logging
from getpass import getpass
from pathlib import Path
from secrets import token_urlsafe

from sqlalchemy import URL

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="生成本机 PostgreSQL 配置，不覆盖已有文件")
    parser.add_argument("--test", action="store_true", help="生成专用测试配置")
    parser.add_argument("--host", default="127.0.0.1", help="数据库主机")
    parser.add_argument("--port", type=int, default=5432, help="数据库端口")
    parser.add_argument("--username", help="数据库用户，默认 after_sales 或 after_sales_test")
    parser.add_argument("--database", help="数据库名，默认 after_sales 或 after_sales_test")
    args = parser.parse_args()
    default_name = "after_sales_test" if args.test else "after_sales"
    database = args.database or default_name
    if args.test and not database.endswith("_test"):
        raise SystemExit("测试库名必须以 _test 结尾")
    if not 1 <= args.port <= 65535:
        raise SystemExit("数据库端口必须在 1～65535 之间")
    filename = ".env.test" if args.test else ".env"
    target = Path(__file__).resolve().parents[1] / filename
    if target.exists():
        raise SystemExit(f"{filename} 已存在，请在编辑器中修改已有配置")
    password = getpass("数据库用户密码（不会显示）：")
    if not password:
        raise SystemExit("数据库密码不能为空")
    url = URL.create(
        "postgresql+psycopg", username=args.username or default_name,
        password=password, host=args.host, port=args.port, database=database,
    ).render_as_string(hide_password=False)
    with target.open("x", encoding="utf-8") as file:
        if args.test:
            file.write(f"TEST_DATABASE_URL={url}\n")
        else:
            file.write(f"DATABASE_URL={url}\nJWT_SECRET={token_urlsafe(48)}\nACCESS_TOKEN_MINUTES=480\n")
    target.chmod(0o600)
    logger.info("已生成 backend/%s，配置值不会输出到终端", filename)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
