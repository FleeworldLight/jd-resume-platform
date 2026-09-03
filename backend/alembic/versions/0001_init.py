"""init schema: pgvector + 所有表 + 索引

Revision ID: 0001_init
Revises:
Create Date: 2026-09-03
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


EMBED_DIM = 1024  # 与 design.md §4 vector(1024) 一致


def upgrade() -> None:
    # 1. pgvector 扩展
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 2. resumes
    op.create_table(
        "resumes",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_path", sa.String(length=512), nullable=True),
        sa.Column("resume_text", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("parse_status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("parse_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # 3. jds
    op.create_table(
        "jds",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("company", sa.String(length=128), nullable=True),
        sa.Column("position", sa.String(length=128), nullable=True),
        sa.Column("salary_min", sa.Integer(), nullable=True),
        sa.Column("salary_max", sa.Integer(), nullable=True),
        sa.Column("city", sa.String(length=128), nullable=True),
        sa.Column("experience", sa.String(length=64), nullable=True),
        sa.Column("education", sa.String(length=64), nullable=True),
        sa.Column("skills", postgresql.JSONB(), nullable=True),
        sa.Column("responsibilities", postgresql.JSONB(), nullable=True),
        sa.Column("requirements", postgresql.JSONB(), nullable=True),
        sa.Column("structured", postgresql.JSONB(), nullable=True),
        sa.Column("crawl_status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("crawl_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_jds_source", "jds", ["source"])
    op.create_index("idx_jds_company_position", "jds", ["company", "position"])

    # 4. customizations
    op.create_table(
        "customizations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("jd_id", sa.BigInteger(), sa.ForeignKey("jds.id"), nullable=False),
        sa.Column("base_resume_id", sa.BigInteger(), sa.ForeignKey("resumes.id"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("gap_report", postgresql.JSONB(), nullable=True),
        sa.Column("customized_resume", postgresql.JSONB(), nullable=True),
        sa.Column("prediction", postgresql.JSONB(), nullable=True),
        sa.Column("retrieval_metrics", postgresql.JSONB(), nullable=True),
        sa.Column("matched_resumes", postgresql.JSONB(), nullable=True),
        sa.Column("provider_used", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_customizations_jd_id", "customizations", ["jd_id"])
    op.create_index("idx_customizations_status", "customizations", ["status"])

    # 5. resume_vectors（pgvector + tsvector 混合召回）
    op.create_table(
        "resume_vectors",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("resume_id", sa.BigInteger(), sa.ForeignKey("resumes.id"), nullable=False, unique=True),
        sa.Column("embedding", Vector(EMBED_DIM), nullable=True),
        sa.Column("search_tsv", postgresql.TSVECTOR(), nullable=True),
        sa.Column("keywords", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    # 6. 索引（design.md §4）
    op.execute(
        "CREATE INDEX idx_resume_vectors_embedding "
        "ON resume_vectors USING ivfflat (embedding vector_cosine_ops)"
    )
    op.execute(
        "CREATE INDEX idx_resume_vectors_search "
        "ON resume_vectors USING GIN (search_tsv)"
    )

    # 7. evaluation_logs
    op.create_table(
        "evaluation_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("customization_id", sa.BigInteger(), nullable=True),
        sa.Column("strategy", sa.String(length=32), nullable=True),
        sa.Column("metrics", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # 8. llm_providers
    op.create_table(
        "llm_providers",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=64), nullable=False, unique=True),
        sa.Column("provider_type", sa.String(length=32), nullable=False),
        sa.Column("base_url", sa.String(length=512), nullable=True),
        sa.Column("api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("chat_model", sa.String(length=128), nullable=True),
        sa.Column("embedding_model", sa.String(length=128), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("llm_providers")
    op.drop_table("evaluation_logs")
    op.drop_index("idx_resume_vectors_search", table_name="resume_vectors")
    op.drop_index("idx_resume_vectors_embedding", table_name="resume_vectors")
    op.drop_table("resume_vectors")
    op.drop_index("idx_customizations_status", table_name="customizations")
    op.drop_index("idx_customizations_jd_id", table_name="customizations")
    op.drop_table("customizations")
    op.drop_index("idx_jds_company_position", table_name="jds")
    op.drop_index("idx_jds_source", table_name="jds")
    op.drop_table("jds")
    op.drop_table("resumes")
    # 不 drop extension，留给运维
