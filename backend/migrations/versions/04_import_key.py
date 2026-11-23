"""为 CSV 导入增加来源编号，保留已有工单。"""

import sqlalchemy as sa
from alembic import op

revision = "04_import_key"
down_revision = "1368452a803a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("import_key", sa.String(100), nullable=True))
    op.create_unique_constraint("tickets_import_key_key", "tickets", ["import_key"])


def downgrade() -> None:
    op.drop_constraint("tickets_import_key_key", "tickets", type_="unique")
    op.drop_column("tickets", "import_key")
