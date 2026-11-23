from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.core.pagination import Page, PageSize
from app.core.security import AdminUser, CurrentUser, DbSession
from app.models import Product, ProductModule, TicketCategory
from app.modules.config.schemas import ModuleCreate, ModuleResponse, NamedCreate, NamedResponse, NamedUpdate

router = APIRouter(prefix="/api/config", tags=["基础配置"])


@router.get("/products", response_model=list[NamedResponse])
async def products(db: DbSession, user: CurrentUser, page: Page = 1, page_size: PageSize = 100) -> list[NamedResponse]:
    rows = await db.scalars(select(Product).order_by(Product.id).offset((page - 1) * page_size).limit(page_size))
    return [NamedResponse.model_validate(item) for item in rows]


@router.post("/products", response_model=NamedResponse, status_code=201)
async def create_product(body: NamedCreate, db: DbSession, admin: AdminUser) -> NamedResponse:
    product = Product(name=body.name)
    db.add(product)
    await db.commit()
    return NamedResponse.model_validate(product)


@router.put("/products/{product_id}", response_model=NamedResponse)
async def update_product(product_id: int, body: NamedUpdate, db: DbSession, admin: AdminUser) -> NamedResponse:
    product = await db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="产品不存在")
    product.name, product.is_active = body.name, body.is_active
    await db.commit()
    return NamedResponse.model_validate(product)


@router.get("/modules", response_model=list[ModuleResponse])
async def modules(db: DbSession, user: CurrentUser, page: Page = 1, page_size: PageSize = 100) -> list[ModuleResponse]:
    rows = await db.scalars(
        select(ProductModule).order_by(ProductModule.id).offset((page - 1) * page_size).limit(page_size)
    )
    return [ModuleResponse.model_validate(item) for item in rows]


@router.post("/modules", response_model=ModuleResponse, status_code=201)
async def create_module(body: ModuleCreate, db: DbSession, admin: AdminUser) -> ModuleResponse:
    product = await db.get(Product, body.product_id)
    if product is None or not product.is_active:
        raise HTTPException(status_code=422, detail="请选择启用的产品")
    module = ProductModule(name=body.name, product_id=body.product_id)
    db.add(module)
    await db.commit()
    return ModuleResponse.model_validate(module)


@router.put("/modules/{module_id}", response_model=ModuleResponse)
async def update_module(module_id: int, body: NamedUpdate, db: DbSession, admin: AdminUser) -> ModuleResponse:
    module = await db.get(ProductModule, module_id)
    if module is None:
        raise HTTPException(status_code=404, detail="模块不存在")
    module.name, module.is_active = body.name, body.is_active
    await db.commit()
    return ModuleResponse.model_validate(module)


@router.get("/categories", response_model=list[NamedResponse])
async def categories(
    db: DbSession, user: CurrentUser, page: Page = 1, page_size: PageSize = 100
) -> list[NamedResponse]:
    rows = await db.scalars(
        select(TicketCategory).order_by(TicketCategory.id).offset((page - 1) * page_size).limit(page_size)
    )
    return [NamedResponse.model_validate(item) for item in rows]


@router.post("/categories", response_model=NamedResponse, status_code=201)
async def create_category(body: NamedCreate, db: DbSession, admin: AdminUser) -> NamedResponse:
    category = TicketCategory(name=body.name)
    db.add(category)
    await db.commit()
    return NamedResponse.model_validate(category)


@router.put("/categories/{category_id}", response_model=NamedResponse)
async def update_category(category_id: int, body: NamedUpdate, db: DbSession, admin: AdminUser) -> NamedResponse:
    category = await db.get(TicketCategory, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="分类不存在")
    category.name, category.is_active = body.name, body.is_active
    await db.commit()
    return NamedResponse.model_validate(category)
