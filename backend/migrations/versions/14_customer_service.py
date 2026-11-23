"""客户身份、客服级别与会话转人工关联。"""

import sqlalchemy as sa
from alembic import op

revision = "14_customer_service"
down_revision = "13_qa_conversations"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("users_role_check", "users", type_="check")
    op.create_check_constraint("users_role_check", "users", "role IN ('admin','staff','customer')")
    op.add_column("users", sa.Column("customer_tier", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("users", sa.Column("staff_level", sa.Integer(), nullable=False, server_default="1"))
    op.create_check_constraint("users_customer_tier_check", "users", "customer_tier BETWEEN 1 AND 4")
    op.create_check_constraint("users_staff_level_check", "users", "staff_level BETWEEN 1 AND 3")
    op.alter_column("tickets", "owner_id", nullable=True)
    op.add_column("tickets", sa.Column("customer_id", sa.Integer(), sa.ForeignKey("users.id")))
    op.create_index("ix_tickets_customer_id", "tickets", ["customer_id"])
    op.add_column("tickets", sa.Column("required_level", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("tickets", sa.Column("previous_owner_id", sa.Integer(), sa.ForeignKey("users.id")))
    op.add_column("qa_conversations", sa.Column("ticket_id", sa.Integer(), sa.ForeignKey("tickets.id")))
    op.create_unique_constraint("qa_conversations_ticket_id_key", "qa_conversations", ["ticket_id"])


def downgrade():
    connection = op.get_bind()
    has_service_data = connection.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM users WHERE role = 'customer' OR staff_level <> 1) "
            "OR EXISTS (SELECT 1 FROM tickets WHERE customer_id IS NOT NULL OR owner_id IS NULL)"
        )
    )
    if has_service_data:
        raise RuntimeError("已有客户服务数据，降级前请制定数据迁移方案")
    op.drop_constraint("qa_conversations_ticket_id_key", "qa_conversations", type_="unique")
    op.drop_column("qa_conversations", "ticket_id")
    op.drop_column("tickets", "previous_owner_id")
    op.drop_column("tickets", "required_level")
    op.drop_index("ix_tickets_customer_id", table_name="tickets")
    op.drop_column("tickets", "customer_id")
    op.alter_column("tickets", "owner_id", nullable=False)
    op.drop_constraint("users_staff_level_check", "users", type_="check")
    op.drop_constraint("users_customer_tier_check", "users", type_="check")
    op.drop_column("users", "staff_level")
    op.drop_column("users", "customer_tier")
    op.drop_constraint("users_role_check", "users", type_="check")
    op.create_check_constraint("users_role_check", "users", "role IN ('admin','staff')")
