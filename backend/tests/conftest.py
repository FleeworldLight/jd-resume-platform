"""pytest fixtures：使用纯逻辑测试，不需要 DB。

W2 阶段：单元测试聚焦：
- 爬虫 factory（URL → source 识别）
- Pydantic schema 校验
- Prompt 模板渲染
- 异常 → Result.fail 转换
- 业务异常抛出
"""
from __future__ import annotations

import os

# 测试环境：先设置 env，再 import app.*
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DATABASE_SYNC_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_DEFAULT_PROVIDER", "mock")
os.environ.setdefault("EMBEDDING_DIM", "1024")
