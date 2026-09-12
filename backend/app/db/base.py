"""SQLAlchemy 2.0 声明性基类。"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    """不带时区信息的 UTC 时间（与 SQLite CURRENT_TIMESTAMP 口径一致）。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""

    pass


class TimestampMixin:
    """created_at / updated_at 公共字段。

    这里刻意使用 **Python 侧** 的 default / onupdate，而不是
    ``server_default=func.now()`` / ``onupdate=func.now()``。

    原因：服务端表达式（server-side onupdate）会让 SQLAlchemy 在 UPDATE 之后把该列
    标记为「已过期」，下次读取属性时必须再发一次 SELECT。若这次读取发生在异步会话
    上下文之外——典型场景是 FastAPI 把 ORM 对象交给 Pydantic 做 ``model_validate``
    序列化——就会抛 ``MissingGreenlet: greenlet_spawn has not been called``。

    改成 Python 侧赋值后，值在 flush 时就写入对象内存，永远不会过期，也就不存在
    「序列化时触发惰性 IO」的问题。
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )
