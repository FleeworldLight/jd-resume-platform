"""测试用 Embedding：稳定 + 归一化的伪向量。

特点：
- 同样文本 → 同样向量（可重现）
- 文本间余弦相似度反映字符重合度（足够用于 e2e 冒烟）
- 维度可配
"""
from __future__ import annotations

import hashlib
import math

from langchain_core.embeddings import Embeddings


class FakeEmbeddings(Embeddings):
    def __init__(self, dim: int = 1024) -> None:
        self.dim = dim

    def _vec(self, text: str) -> list[float]:
        # 用 hash 派生 dim 个伪随机分量，再 L2 归一化
        seed = hashlib.sha256(text.encode("utf-8")).digest()
        # 扩展到足够字节
        raw = (seed * ((self.dim // len(seed)) + 1))[: self.dim]
        v = [b / 255.0 for b in raw]
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)
