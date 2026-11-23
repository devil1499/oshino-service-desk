"""记录真实解决时刻，历史缺失时间不编造。"""

import sqlalchemy as sa
from alembic import op

revision = "09_resolution_time"
down_revision = "07_assistance"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tickets", sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("""UPDATE tickets t SET resolved_at = r.solved_at FROM
        (SELECT ticket_id, min(created_at) AS solved_at FROM ticket_records
         WHERE kind='status' AND content='保存解决方案：处理中 → 已解决'
         GROUP BY ticket_id) r
        WHERE t.id=r.ticket_id AND t.status IN ('resolved','closed')
          AND r.solved_at >= t.created_at""")


def downgrade():
    op.drop_column("tickets", "resolved_at")
