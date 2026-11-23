"""保存每轮联网模式，历史消息默认仅知识库。"""

import sqlalchemy as sa
from alembic import op

revision = "16_web_search"
down_revision = "15_qa_observability"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("qa_messages", sa.Column("web_search", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("qa_messages", "web_search")
