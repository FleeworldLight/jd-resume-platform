-- 启用 pgvector（向量检索）
CREATE EXTENSION IF NOT EXISTS vector;

-- 启用 zhparser（中文分词）
-- pgvector 镜像未必带 zhparser，DO 块容错
DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS zhparser;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'zhparser 扩展安装失败，跳过（无中文全文检索支持）';
END
$$;
