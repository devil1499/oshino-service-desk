"""创建用户与基础配置四张表，与教程第二部分保持同一迁移编号。"""

import sqlalchemy as sa
from alembic import op

revision = "321917cab056"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="products_pkey"),
        sa.UniqueConstraint("name", name="products_name_key"),
    )
    op.create_table(
        "ticket_categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="ticket_categories_pkey"),
        sa.UniqueConstraint("name", name="ticket_categories_name_key"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(50), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("role IN ('admin', 'staff')", name="users_role_check"),
        sa.PrimaryKeyConstraint("id", name="users_pkey"),
        sa.UniqueConstraint("username", name="users_username_key"),
    )
    op.create_table(
        "product_modules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="product_modules_product_id_fkey"),
        sa.PrimaryKeyConstraint("id", name="product_modules_pkey"),
        sa.UniqueConstraint("product_id", "name", name="modules_product_name_key"),
    )


def downgrade() -> None:
    op.drop_table("product_modules")
    op.drop_table("users")
    op.drop_table("ticket_categories")
    op.drop_table("products")
