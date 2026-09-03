"""Celery 应用对象。

设计文档 §6.3 + docs/architecture/async-tasks.md。
任务 = Service 调用的薄包装；通过 task_prerun 注入新 event loop 和 DB session。
"""
from __future__ import annotations

import asyncio

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "jd_platform",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.tasks.resume_tasks",
        "app.tasks.jd_tasks",
        "app.tasks.customization_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=False,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # 开发/无 broker 环境走 eager 模式，task.delay() 立即同步执行
    task_always_eager=False,
    task_eager_propagates=True,
)


def run_async(coro):
    """在 Celery worker（同步上下文）里跑 async 协程。"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
