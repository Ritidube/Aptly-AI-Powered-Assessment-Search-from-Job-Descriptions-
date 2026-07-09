"""initial persistence tables

Revision ID: 0001
Revises:
Create Date: 2026-07-07

"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("conversation_key", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("conversation_key", name="uq_conversations_conversation_key"),
    )
    op.create_index(
        "ix_conversations_conversation_key", "conversations", ["conversation_key"], unique=True
    )

    op.create_table(
        "request_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("route_label", sa.String(length=32), nullable=False),
        sa.Column("model_tier", sa.String(length=16), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("end_of_conversation", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_user_message", sa.Text(), nullable=False),
        sa.Column("reply_text", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_request_logs_conversation_id", "request_logs", ["conversation_id"])
    op.create_index("ix_request_logs_created_at", "request_logs", ["created_at"])
    op.create_index("ix_request_logs_route_label", "request_logs", ["route_label"])

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_log_id", sa.Integer(), sa.ForeignKey("request_logs.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
    )
    op.create_index("ix_messages_request_log_id", "messages", ["request_log_id"])

    op.create_table(
        "recommendations_shown",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_log_id", sa.Integer(), sa.ForeignKey("request_logs.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("test_type", sa.String(length=16), nullable=True),
    )
    op.create_index(
        "ix_recommendations_shown_request_log_id", "recommendations_shown", ["request_log_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_recommendations_shown_request_log_id", table_name="recommendations_shown")
    op.drop_table("recommendations_shown")

    op.drop_index("ix_messages_request_log_id", table_name="messages")
    op.drop_table("messages")

    op.drop_index("ix_request_logs_route_label", table_name="request_logs")
    op.drop_index("ix_request_logs_created_at", table_name="request_logs")
    op.drop_index("ix_request_logs_conversation_id", table_name="request_logs")
    op.drop_table("request_logs")

    op.drop_index("ix_conversations_conversation_key", table_name="conversations")
    op.drop_table("conversations")
