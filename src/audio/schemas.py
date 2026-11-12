"""音频转写模块的数据模型。

这些模型同时也是 HTTP 接口的响应结构，所以字段命名保持前端可直接使用。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Segment(BaseModel):
    """一个分句（whisper 的 segment），时间单位是秒。"""

    id: int
    start: float
    end: float
    text: str


class TranscriptionResult(BaseModel):
    """一次转写的完整结果。"""

    text: str = Field(description="整段转写文本")
    language: str | None = Field(default=None, description="识别出的语言代码，如 zh、en")
    language_probability: float | None = Field(default=None, description="语言识别置信度")
    duration: float | None = Field(default=None, description="音频时长（秒）")
    segments: list[Segment] = Field(default_factory=list, description="带时间戳的分句")


class TaskStatus(str, Enum):
    """异步转写任务的四种状态。"""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskResponse(BaseModel):
    """任务查询接口的响应。任务完成前 result 为空，失败时 error 有值。"""

    task_id: str
    status: TaskStatus
    created_at: datetime
    finished_at: datetime | None = None
    result: TranscriptionResult | None = None
    error: str | None = None
