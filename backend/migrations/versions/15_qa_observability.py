"""问答运行记录与人工评测；历史回答不补造遥测数据。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "15_qa_observability"
down_revision = "14_customer_service"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("qa_messages", sa.Column("run_details", JSONB(), nullable=True))
    op.add_column(
        "qa_conversations", sa.Column("is_evaluation", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.create_table(
        "qa_evaluation_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("suite_version", sa.String(50), nullable=False),
        sa.Column("cases", JSONB(), nullable=False),
        sa.Column("results", JSONB(), nullable=False),
        sa.Column("active_case", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_qa_evaluation_runs_owner_id", "qa_evaluation_runs", ["owner_id"])


def downgrade():
    op.drop_index("ix_qa_evaluation_runs_owner_id", table_name="qa_evaluation_runs")
    op.drop_table("qa_evaluation_runs")
    op.drop_column("qa_conversations", "is_evaluation")
    op.drop_column("qa_messages", "run_details")
