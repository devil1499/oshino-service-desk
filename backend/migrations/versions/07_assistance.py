"""生成快照与人工采用记录。"""

import sqlalchemy as sa
from alembic import op

revision = "07_assistance"
down_revision = "06_knowledge"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "assistance_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticket_id", sa.Integer(), sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("author_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("ticket_fingerprint", sa.String(64), nullable=False),
        sa.Column("draft", sa.JSON(), nullable=False),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("prompt_version", sa.String(50), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("adopted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("adopted_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("final_solution", sa.Text(), nullable=True),
        sa.Column("final_reply", sa.Text(), nullable=True),
    )
    op.create_index("ix_assistance_runs_ticket_id", "assistance_runs", ["ticket_id"])


def downgrade():
    op.drop_table("assistance_runs")
