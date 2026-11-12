"""转写任务服务。

FastAPI 路由只负责校验请求和拼响应，真正的任务状态管理与转写调用都在这里，
这样核心逻辑可以脱离 HTTP 被其他模块调用，也方便测试。
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from fastapi import UploadFile

from .engine import Transcriber
from .schemas import TaskResponse, TaskStatus, TranscriptionResult

logger = logging.getLogger(__name__)

# 接受的上传格式。视频由视频模块先抽音轨，这里只处理音频。
ALLOWED_SUFFIXES = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus", ".webm", ".aac"}

# 分块读取上传文件时每块的大小
CHUNK_SIZE = 1024 * 1024


class UnsupportedAudioFormatError(Exception):
    """上传的文件扩展名不在支持范围内。"""


class AudioTooLargeError(Exception):
    """上传文件超过大小上限。"""


class TaskNotFoundError(Exception):
    """查询的任务 id 不存在。"""


@dataclass
class _Task:
    """内部任务记录。对外只暴露 TaskResponse。"""

    id: str
    status: TaskStatus
    created_at: datetime
    finished_at: datetime | None = None
    result: TranscriptionResult | None = None
    error: str | None = None
    audio_path: Path | None = None

    def to_response(self) -> TaskResponse:
        return TaskResponse(
            task_id=self.id,
            status=self.status,
            created_at=self.created_at,
            finished_at=self.finished_at,
            result=self.result,
            error=self.error,
        )


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TranscriptionService:
    """管理转写任务的生命周期。

    任务记录保存在进程内存里：开发阶段单进程足够，服务重启后未完成的任务会丢失。
    """

    def __init__(self, transcriber: Transcriber, upload_dir: Path, max_upload_mb: int) -> None:
        self._transcriber = transcriber
        self._upload_dir = upload_dir
        self._max_upload_bytes = max_upload_mb * 1024 * 1024
        self._tasks: dict[str, _Task] = {}
        self._lock = threading.Lock()
        self._upload_dir.mkdir(parents=True, exist_ok=True)

    async def submit(self, file: UploadFile, language: str | None = None) -> TaskResponse:
        """保存上传的音频并登记一个排队中的任务。"""
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            raise UnsupportedAudioFormatError(
                f"不支持的音频格式：{suffix or '未知'}，支持 {', '.join(sorted(ALLOWED_SUFFIXES))}"
            )

        task_id = uuid.uuid4().hex
        audio_path = self._upload_dir / f"{task_id}{suffix}"
        await self._save_audio(file, audio_path)

        task = _Task(id=task_id, status=TaskStatus.QUEUED, created_at=_now(), audio_path=audio_path)
        with self._lock:
            self._tasks[task_id] = task
        logger.info("收到转写任务 %s（%s）", task_id, audio_path.name)
        return task.to_response()

    async def _save_audio(self, file: UploadFile, audio_path: Path) -> None:
        """分块写入临时文件，超过大小上限时删掉文件并报错。"""
        written = 0
        try:
            with audio_path.open("wb") as output:
                while chunk := await file.read(CHUNK_SIZE):
                    written += len(chunk)
                    if written > self._max_upload_bytes:
                        raise AudioTooLargeError(
                            f"音频超过大小上限 {self._max_upload_bytes // (1024 * 1024)}MB"
                        )
                    output.write(chunk)
        except BaseException:
            audio_path.unlink(missing_ok=True)
            raise

    def process(self, task_id: str, language: str | None = None) -> None:
        """执行转写（同步阻塞，由调用方放到线程里跑）。转写完成后删除音频文件。"""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                logger.warning("转写任务 %s 已不存在，跳过", task_id)
                return
            task.status = TaskStatus.PROCESSING

        try:
            assert task.audio_path is not None
            result = self._transcriber.transcribe(task.audio_path, language=language)
        except Exception as exc:  # 转写失败不抛出，写进任务状态供轮询方读取
            logger.exception("转写任务 %s 失败", task_id)
            with self._lock:
                task.status = TaskStatus.FAILED
                task.error = f"{type(exc).__name__}: {exc}"
                task.finished_at = _now()
        else:
            with self._lock:
                task.status = TaskStatus.COMPLETED
                task.result = result
                task.finished_at = _now()
            logger.info("转写任务 %s 完成，文本长度 %d", task_id, len(result.text))
        finally:
            if task.audio_path is not None:
                task.audio_path.unlink(missing_ok=True)
                task.audio_path = None

    def get(self, task_id: str) -> TaskResponse:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise TaskNotFoundError(task_id)
            return task.to_response()
