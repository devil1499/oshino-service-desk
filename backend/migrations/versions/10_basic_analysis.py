import sqlalchemy as sa
from alembic import op

revision = "10_basic_analysis"
down_revision = "09_resolution_time"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "basic_analyses",
        sa.Column("ticket_id", sa.Integer(), sa.ForeignKey("tickets.id"), primary_key=True),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("model", sa.String(200), nullable=True),
        sa.Column("prompt_version", sa.String(50), nullable=False),
        sa.Column("adopted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('pending','running','completed','failed')", name="basic_status_check"
        ),
    )


def downgrade():
    op.drop_table("basic_analyses")
