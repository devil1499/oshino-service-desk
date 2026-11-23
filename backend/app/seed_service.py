"""创建明确标识的演示人员与产品，重复运行不修改现有密码。"""

import asyncio
import json
import secrets
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import create_database_engine
from app.core.passwords import PasswordService
from app.core.settings import Settings
from app.models import KnowledgeChunk, KnowledgeDocument, Product, ProductModule, TicketCategory, User
from app.modules.knowledge.text import document_fingerprint, split_text

PEOPLE = [
    ("demo_bronze", "演示客户·小陈", "customer", 1, 1),
    ("demo_platinum", "演示客户·林同学", "customer", 2, 1),
    ("demo_king", "演示客户·小许", "customer", 3, 1),
    ("demo_champion", "演示客户·小赵", "customer", 4, 1),
    ("demo_l1_lin", "小林", "staff", 1, 1),
    ("demo_l1_li", "小李", "staff", 1, 1),
    ("demo_l2_zhou", "小周", "staff", 1, 2),
    ("demo_l3_wang", "王主管", "staff", 1, 3),
]


async def seed(settings, credential_path: Path):
    engine = create_database_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    exists = await asyncio.to_thread(credential_path.exists)
    saved = json.loads(await asyncio.to_thread(credential_path.read_text, encoding="utf-8")) if exists else []
    passwords = PasswordService()
    try:
        async with factory.begin() as db:
            for username, name, role, tier, level in PEOPLE:
                if await db.scalar(select(User.id).where(User.username == username)):
                    continue
                password = secrets.token_urlsafe(15)
                db.add(
                    User(
                        username=username,
                        display_name=name,
                        role=role,
                        customer_tier=tier,
                        staff_level=level,
                        is_active=True,
                        password_hash=await passwords.hash(password),
                    )
                )
                saved.append(dict(username=username, name=name, role=role, tier=tier, level=level, password=password))
            category = await db.scalar(select(TicketCategory).where(TicketCategory.name == "待人工分类"))
            if category is None:
                category = TicketCategory(name="待人工分类")
                db.add(category)
                await db.flush()
            for name in ["Oshino Air 蓝牙耳机", "Oshino Air Pro 蓝牙耳机"]:
                product = await db.scalar(select(Product).where(Product.name == name))
                if product is None:
                    product = Product(name=name)
                    db.add(product)
                    await db.flush()
                module = await db.scalar(
                    select(ProductModule).where(
                        ProductModule.product_id == product.id, ProductModule.name == "售后服务"
                    )
                )
                if module is None:
                    module = ProductModule(product_id=product.id, name="售后服务")
                    db.add(module)
                    await db.flush()
                title = name + "·演示使用与售后规则"
                if await db.scalar(select(KnowledgeDocument.id).where(KnowledgeDocument.title == title)):
                    continue
                content = (
                    f"# {name}（虚构产品，毕业设计演示）\n"
                    "## 蓝牙连接问题\n确认耳机有电并进入配对模式，打开手机蓝牙查找产品名称。"
                    "如曾配对，先在手机移除旧配对记录再重新配对；仍失败时记录手机型号、系统版本和指示灯状态，转人工排查。\n"
                    "## 单边无声\n检查手机声道平衡、两只耳机电量和充电接触情况。"
                    "记录异常出现时间，交技术客服进一步核实。\n"
                    "## 人工服务\n用户可输入转人工。L1处理常见咨询，L2处理技术故障，L3处理投诉和协调。"
                    "用户不满意可申请更换客服，沿用原工单和记录。具体退款、保修和维修结论需人工核实，不承诺已经执行。"
                )
                doc = KnowledgeDocument(
                    title=title,
                    content=content,
                    source_name="项目演示规则",
                    product_id=product.id,
                    module_id=module.id,
                    category_id=category.id,
                    revision=1,
                    status="published",
                    chunk_count=len(split_text(content)),
                )
                db.add(doc)
                await db.flush()
                db.add_all(
                    KnowledgeChunk(
                        document_id=doc.id, chunk_order=i, content=text, fingerprint=document_fingerprint(doc)
                    )
                    for i, text in enumerate(split_text(content), 1)
                )
            # 文件位于 .local 或 /tmp，仅供本机验收；不将密码输出至日志。
            credential_path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(
                credential_path.write_text, json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8"
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--credentials", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(seed(Settings.load(), args.credentials))
    print("演示人员与产品已准备，账号文件已写入指定本地位置。")
