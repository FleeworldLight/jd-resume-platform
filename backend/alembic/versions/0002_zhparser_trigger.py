"""0002: zhparser + 自动维护 search_tsv 触发器。

设计文档 retrieval.md §3.1：中文分词配置 + 触发器。
降级策略：zhparser 扩展可能装不上，触发器函数必须能在没有 chinese 配置的情况下工作。
"""
from __future__ import annotations

from alembic import op

# revision identifiers
revision = "0002_zhparser_trigger"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. zhparser 扩展（如果没装，try/except 兜底，不阻塞升级）
    op.execute("CREATE EXTENSION IF NOT EXISTS zhparser")

    # 2. chinese 全文检索配置（如果不存在则创建）
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_ts_config WHERE cfgname = 'chinese') THEN
                CREATE TEXT SEARCH CONFIGURATION chinese (PARSER = zhparser);
                ALTER TEXT SEARCH CONFIGURATION chinese
                    ADD MAPPING FOR n, v, a, i, e, l, t WITH simple;
            END IF;
        END
        $$;
        """
    )

    # 3. 触发器函数：自动维护 resume_vectors.search_tsv
    op.execute(
        """
        CREATE OR REPLACE FUNCTION update_resume_search_tsv()
        RETURNS TRIGGER AS $func$
        BEGIN
            -- 优先用 chinese（需 zhparser），否则 simple 兜底
            BEGIN
                NEW.search_tsv :=
                    setweight(to_tsvector('chinese', COALESCE(NEW.keywords::text, '')), 'A') ||
                    setweight(
                        to_tsvector(
                            'chinese',
                            COALESCE(
                                (SELECT resume_text FROM resumes WHERE id = NEW.resume_id),
                                ''
                            )
                        ),
                        'B'
                    );
            EXCEPTION WHEN OTHERS THEN
                NEW.search_tsv :=
                    setweight(to_tsvector('simple', COALESCE(NEW.keywords::text, '')), 'A') ||
                    setweight(
                        to_tsvector(
                            'simple',
                            COALESCE(
                                (SELECT resume_text FROM resumes WHERE id = NEW.resume_id),
                                ''
                            )
                        ),
                        'B'
                    );
            END;
            RETURN NEW;
        END;
        $func$ LANGUAGE plpgsql;
        """
    )

    # 4. 触发器：BEFORE INSERT OR UPDATE
    op.execute("DROP TRIGGER IF EXISTS trg_update_resume_search_tsv ON resume_vectors")
    op.execute(
        """
        CREATE TRIGGER trg_update_resume_search_tsv
        BEFORE INSERT OR UPDATE OF keywords, resume_id ON resume_vectors
        FOR EACH ROW EXECUTE FUNCTION update_resume_search_tsv();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_update_resume_search_tsv ON resume_vectors")
    op.execute("DROP FUNCTION IF EXISTS update_resume_search_tsv()")
    # 不 drop 扩展和配置，运维统一管理
