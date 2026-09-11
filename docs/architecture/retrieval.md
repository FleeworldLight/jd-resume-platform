# 召回引擎设计

> **文档状态：部分过时（2026-09-11 标注）**
>
> 本文写于项目采用 Docker + PostgreSQL + pgvector + Redis + Celery 架构的阶段。
> 当前实际架构已简化为 SQLite + mock LLM provider + 无 Celery 的同步执行，详见根目录 README.md。
> 下文涉及 Docker / Postgres / pgvector / Redis / Celery / weasyprint 的段落仅作历史设计参考，不代表现状。

> PostgreSQL + pgvector + 全文检索 + 自研混合打分。
> 替代 Lucene / ElasticSearch，零额外依赖。

---

## 1. 核心思路

**两层召回 + 混合打分**：

```
Query (JD 文本)
  ↓
[Layer 1: 向量召回] pgvector (cosine, TopK=100)
  ↓ + 0.6 权重
[Layer 2: 关键词召回] PG tsvector (BM25, TopK=100)
  ↓ + 0.4 权重
[混合打分] 加权求和 + 归一化
  ↓
TopK=50 返回
```

**为什么这套组合**：
- 向量召回：抓语义相似（"高并发" ≈ "高 QPS"）
- 关键词召回：抓精确匹配（"Kafka" 命中关键词）
- 混合：兼顾两者

---

## 2. 向量召回（pgvector）

### 2.1 表结构

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE resume_vectors (
    id          BIGSERIAL PRIMARY KEY,
    resume_id   BIGINT UNIQUE NOT NULL,
    embedding   vector(1024),       -- Embedding 模型维度
    search_tsv  tsvector,
    keywords    JSONB,
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);

-- ivfflat 索引（数据量 < 100k 用这个）
CREATE INDEX idx_resume_vectors_embedding
    ON resume_vectors USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 10);
```

### 2.2 Embedding

```python
from langchain_openai import OpenAIEmbeddings
from langchain_community.embeddings import DashScopeEmbeddings

class EmbeddingService:
    def __init__(self, llm_service: LLMService):
        self.llm_service = llm_service
    
    async def embed(self, text: str) -> list[float]:
        """调 Embedding 模型，返回 1024 维向量"""
        embeddings = await self.llm_service.get_embedding_model()
        return await embeddings.aembed_query(text)
    
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量 Embedding"""
        embeddings = await self.llm_service.get_embedding_model()
        return await embeddings.aembed_documents(texts)
```

### 2.3 向量检索 SQL

```python
VECTOR_SEARCH_SQL = """
    SELECT resume_id,
           1 - (embedding <=> :query_vec::vector) AS score
    FROM resume_vectors
    ORDER BY embedding <=> :query_vec::vector
    LIMIT :top_k
"""
```

```python
async def vector_search(self, query: str, top_k: int) -> list[ResumeScore]:
    query_vec = await self.embedding_service.embed(query)
    
    rows = await self.db.execute(
        text(VECTOR_SEARCH_SQL),
        {"query_vec": str(query_vec), "top_k": top_k}
    )
    return [ResumeScore(resume_id=r[0], score=float(r[1])) for r in rows.fetchall()]
```

---

## 3. 关键词召回（PG tsvector + zhparser）

### 3.1 中文分词配置

```sql
-- 安装 zhparser 扩展
CREATE EXTENSION zhparser;

-- 创建中文全文检索配置
CREATE TEXT SEARCH CONFIGURATION chinese (PARSER = zhparser);
ALTER TEXT SEARCH CONFIGURATION chinese
    ADD MAPPING FOR n, v, a, i, e, l, t WITH simple;

-- 创建触发器自动维护 tsvector
CREATE OR REPLACE FUNCTION update_resume_search_tsv()
RETURNS TRIGGER AS $$
BEGIN
    NEW.search_tsv :=
        setweight(to_tsvector('chinese', COALESCE(NEW.keywords::text, '')), 'A') ||
        setweight(to_tsvector('chinese', COALESCE(
            (SELECT resume_text FROM resumes WHERE id = NEW.resume_id), ''
        )), 'B');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_update_resume_search_tsv
    BEFORE INSERT OR UPDATE ON resume_vectors
    FOR EACH ROW EXECUTE FUNCTION update_resume_search_tsv();
```

### 3.2 GIN 索引

```sql
CREATE INDEX idx_resume_vectors_search ON resume_vectors USING GIN (search_tsv);
```

### 3.3 关键词检索 SQL

PG 的 `ts_rank_cd` 类似 BM25：

```python
KEYWORD_SEARCH_SQL = """
    SELECT resume_id,
           ts_rank_cd(search_tsv, query) AS score
    FROM resume_vectors, plainto_tsquery('chinese', :query) AS query
    WHERE search_tsv @@ query
    ORDER BY score DESC
    LIMIT :top_k
"""
```

```python
async def keyword_search(self, query: str, top_k: int) -> list[ResumeScore]:
    rows = await self.db.execute(
        text(KEYWORD_SEARCH_SQL),
        {"query": query, "top_k": top_k}
    )
    return [ResumeScore(resume_id=r[0], score=float(r[1])) for r in rows.fetchall()]
```

---

## 4. 混合打分

### 4.1 归一化

向量分数范围 `[0, 1]`，关键词分数范围 `[0, ∞)`，先归一化到 `[0, 1]`：

```python
def normalize_scores(scores: list[ResumeScore]) -> list[ResumeScore]:
    if not scores:
        return []
    max_score = max(s.score for s in scores)
    if max_score == 0:
        return [ResumeScore(s.resume_id, 0.0) for s in scores]
    return [ResumeScore(s.resume_id, s.score / max_score) for s in scores]
```

### 4.2 加权融合

```python
async def hybrid_search(self, query: str, top_k: int) -> list[ResumeScore]:
    # 1. 分别召回（多取一些做候选池）
    vector_results = await self.vector_search(query, top_k=top_k * 2)
    keyword_results = await self.keyword_search(query, top_k=top_k * 2)
    
    # 2. 归一化
    vector_results = normalize_scores(vector_results)
    keyword_results = normalize_scores(keyword_results)
    
    # 3. 加权融合
    merged: dict[int, float] = {}
    for r in vector_results:
        merged[r.resume_id] = merged.get(r.resume_id, 0.0) + 0.6 * r.score
    for r in keyword_results:
        merged[r.resume_id] = merged.get(r.resume_id, 0.0) + 0.4 * r.score
    
    # 4. 排序取 TopK
    sorted_results = sorted(merged.items(), key=lambda x: x[1], reverse=True)
    return [ResumeScore(resume_id=rid, score=score) 
            for rid, score in sorted_results[:top_k]]
```

### 4.3 权重配置

```python
# app/core/config.py
class RetrievalSettings(BaseSettings):
    vector_weight: float = 0.6
    keyword_weight: float = 0.4
    candidate_top_k: int = 100  # 候选池大小
    final_top_k: int = 50      # 最终返回大小
```

---

## 5. 索引构建

### 5.1 简历上传时异步索引

```python
@celery_app.task(bind=True, max_retries=2)
def index_resume_task(self, resume_id: int):
    async def _run():
        async with async_session() as db:
            resume = await get_resume(db, resume_id)
            text = resume.resume_text
            
            # 1. Embedding
            embedding = await embedding_service.embed(text)
            
            # 2. 关键词提取
            keywords = await extract_keywords(text)  # jieba / sklearn
            
            # 3. 写入 resume_vectors（触发器自动建 tsvector）
            await db.execute(
                text("""
                    INSERT INTO resume_vectors (resume_id, embedding, keywords)
                    VALUES (:rid, :emb::vector, :kw::jsonb)
                    ON CONFLICT (resume_id) DO UPDATE
                    SET embedding = EXCLUDED.embedding,
                        keywords = EXCLUDED.keywords,
                        updated_at = now()
                """),
                {"rid": resume_id, "emb": str(embedding), "kw": json.dumps(keywords)}
            )
            await db.commit()
    
    asyncio.run(_run())
```

### 5.2 关键词提取（jieba + TF-IDF）

```python
import jieba
from sklearn.feature_extraction.text import TfidfVectorizer

def extract_keywords(text: str, top_k: int = 20) -> list[str]:
    """提取关键词：jieba 分词 + TF-IDF 排序"""
    words = jieba.lcut(text)
    # 过滤停用词、单字
    words = [w for w in words if len(w) > 1 and w not in STOPWORDS]
    # TF-IDF 计算
    vectorizer = TfidfVectorizer()
    tfidf = vectorizer.fit_transform([" ".join(words)])
    feature_names = vectorizer.get_feature_names_out()
    scores = tfidf.toarray()[0]
    top_indices = scores.argsort()[::-1][:top_k]
    return [feature_names[i] for i in top_indices]
```

---

## 6. 召回引擎完整接口

```python
class RetrievalService:
    def __init__(
        self,
        db: AsyncSession,
        embedding_service: EmbeddingService,
    ):
        self.db = db
        self.embedding_service = embedding_service
    
    async def index_resume(self, resume_id: int, text: str):
        """为简历建立索引"""
        ...
    
    async def vector_search(self, query: str, top_k: int) -> list[ResumeScore]:
        """纯向量召回"""
        ...
    
    async def keyword_search(self, query: str, top_k: int) -> list[ResumeScore]:
        """纯关键词召回"""
        ...
    
    async def hybrid_search(
        self,
        query: str,
        top_k: int,
        strategy: str = "HYBRID"  # VECTOR / KEYWORD / HYBRID
    ) -> RetrievalResult:
        """混合召回（主入口）"""
        if strategy == "VECTOR":
            results = await self.vector_search(query, top_k)
        elif strategy == "KEYWORD":
            results = await self.keyword_search(query, top_k)
        else:
            results = await self._hybrid(query, top_k)
        
        return RetrievalResult(
            results=results,
            strategy=strategy,
            query=query,
        )
```

---

## 7. 性能基准（参考）

| 数据量 | 向量召回 | 关键词召回 | 混合召回 |
|---|---|---|---|
| 100 简历 | < 50ms | < 30ms | < 80ms |
| 1000 简历 | < 100ms | < 50ms | < 150ms |
| 10000 简历 | < 200ms | < 100ms | < 300ms |

PG `ivfflat` 索引在 10k 量级足够，更大可换 HNSW。

---

## 8. 设计权衡

**优点**：
- ✅ 零额外依赖（PG 已经有了）
- ✅ 一个数据库搞定所有数据
- ✅ 中文分词用 zhparser 成熟方案
- ✅ BM25 风格打分 PG 内置

**取舍**：
- ⚠️ 数据量大（百万级）需要换 HNSW 索引
- ⚠️ 跨语言扩展性差（绑定 PG）
- ⚠️ 没有 ElasticSearch 那样的 DSL

**对你这个项目**：
- 简历库 < 1000，完全够用
- 不需要分布式搜索
- 单数据库部署最简单

---

## 9. 面试讲点

1. **"为什么用 PG 不单独搞 ES？"**
   > 简历库小（<1000），PG 全文检索 + pgvector 完全够用，少一个依赖、少一个服务。规模上来再拆。

2. **"向量召回和关键词召回怎么融合？"**
   > 分别召回到 TopK=100，归一化后加权 0.6/0.4 融合，再排序取 TopK=50。归一化很关键，因为两边分数范围不同。

3. **"为什么选 ivfflat 不用 HNSW？"**
   > 数据量小（<10k），ivfflat 索引快、占内存小；HNSW 召回精度高但吃内存，规模大再换。

4. **"BM25 怎么算的？"**
   > PG `ts_rank_cd` 实现了 BM25 风格的 TF-IDF 加权，分词用 zhparser 扩展。