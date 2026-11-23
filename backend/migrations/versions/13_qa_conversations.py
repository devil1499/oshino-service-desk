import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "13_qa_conversations"
down_revision = "11_email"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "qa_conversations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_qa_conversations_owner_id", "qa_conversations", ["owner_id"])
    op.create_table(
        "qa_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("qa_conversations.id"), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("sources", JSONB(), nullable=False),
        sa.Column("error_code", sa.String(40), nullable=True),
        sa.Column("model", sa.String(200), nullable=True),
        sa.Column("prompt_version", sa.String(50), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("conversation_id", "request_id", "role", name="qa_message_request_role_key"),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="qa_message_role_check"),
        sa.CheckConstraint(
            "status IN ('submitted', 'running', 'answered', 'clarification', 'insufficient', 'failed')",
            name="qa_message_status_check",
        ),
    )
    op.create_index("ix_qa_messages_conversation_id", "qa_messages", ["conversation_id"])
    op.create_index(
        "qa_one_running_per_conversation", "qa_messages", ["conversation_id"], unique=True,
        postgresql_where=sa.text("role = 'assistant' AND status = 'running'"),
    )


def downgrade():
    op.drop_table("qa_messages")
    op.drop_table("qa_conversations")
