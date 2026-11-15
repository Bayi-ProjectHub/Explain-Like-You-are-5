"""练习任务编排：上传视频 → 提取音轨 → 复用转写服务 → 汇总模块结果。"""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import UploadFile
from pydantic import BaseModel, Field

from ..audio.schemas import TaskStatus, TranscriptionResult
from ..audio.service import AudioTooLargeError, TaskNotFoundError, TranscriptionService
from .media import MediaError, VIDEO_SUFFIXES, extract_audio
from .vocabulary import Language, Term

logger = logging.getLogger(__name__)


class ModuleState(BaseModel):
    status: Literal["completed", "pending"]
    message: str


class PracticeTask(BaseModel):
    task_id: str
    status: Literal["queued", "extracting", "transcribing", "completed", "failed"]
    created_at: datetime
    finished_at: datetime | None = None
    term: Term
    language: Language
    filename: str
    result: TranscriptionResult | None = None
    modules: dict[str, ModuleState] = Field(default_factory=dict)
    error: str | None = None


class PracticeService:
    def __init__(
        self, transcription_service: TranscriptionService, upload_dir: Path,
        max_upload_mb: int, max_video_seconds: int = 600,
    ) -> None:
        self._audio = transcription_service
        self._upload_dir = upload_dir
        self._max_bytes = max_upload_mb * 1024 * 1024
        self._max_seconds = max_video_seconds
        self._tasks: dict[str, PracticeTask] = {}
        self._paths: dict[str, Path] = {}
        self._lock = threading.Lock()
        # 当前本地模型适合单个练习逐个处理，避免多个视频同时占满内存。
        self._worker = asyncio.Lock()
        upload_dir.mkdir(parents=True, exist_ok=True)

    async def submit(self, file: UploadFile, term: Term, language: Language) -> PracticeTask:
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in VIDEO_SUFFIXES:
            raise MediaError("请选择 MP4、MOV、WebM、MKV 或 M4V 视频。")
        task_id = uuid.uuid4().hex
        path = self._upload_dir / f"{task_id}{suffix}"
        written = 0
        try:
            with path.open("wb") as output:
                while chunk := await file.read(1024 * 1024):
                    written += len(chunk)
                    if written > self._max_bytes:
                        raise AudioTooLargeError(f"视频超过 {self._max_bytes // (1024 * 1024)} MB 上限。")
                    output.write(chunk)
            if not written:
                raise MediaError("视频文件为空，请重新选择。")
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        task = PracticeTask(
            task_id=task_id, status="queued", created_at=datetime.now(timezone.utc),
            term=term, language=language, filename=Path(file.filename or "video").name,
        )
        with self._lock:
            self._tasks[task_id] = task
            self._paths[task_id] = path
        return task.model_copy(deep=True)

    def _update(self, task_id: str, **changes) -> None:
        with self._lock:
            self._tasks[task_id] = self._tasks[task_id].model_copy(update=changes)

    async def process(self, task_id: str) -> None:
        video_path = self._paths[task_id]
        audio_path = video_path.with_suffix(".wav")
        try:
            async with self._worker:
                self._update(task_id, status="extracting")
                await asyncio.to_thread(extract_audio, video_path, audio_path, self._max_seconds)
                self._update(task_id, status="transcribing")
                task = self.get(task_id)
                with audio_path.open("rb") as audio_file:
                    upload = UploadFile(filename="extracted.wav", file=audio_file)
                    transcription = await self._audio.submit(upload, language=task.language)
                audio_path.unlink(missing_ok=True)
                await asyncio.to_thread(self._audio.process, transcription.task_id, task.language)
                completed = self._audio.get(transcription.task_id)
                if completed.status != TaskStatus.COMPLETED or completed.result is None:
                    raise MediaError("语音转写失败，请稍后重试；如持续失败，请检查服务端模型配置。")
                if not completed.result.text.strip():
                    raise MediaError("没有识别到讲话，请检查音量和麦克风后重试。")
                self._update(
                    task_id, status="completed", result=completed.result,
                    finished_at=datetime.now(timezone.utc), modules={
                        "transcription": ModuleState(status="completed", message="音轨提取与语音转写已完成"),
                        "text_evaluation": ModuleState(status="pending", message="文本评价模块待接入，尚未生成评分或建议"),
                        "video_evaluation": ModuleState(status="pending", message="视频评价模块待接入，尚未分析画面或表现"),
                    },
                )
        except Exception as exc:
            logger.exception("练习任务 %s 失败", task_id)
            message = str(exc) if isinstance(exc, MediaError) else "处理遇到问题，请稍后重试。"
            self._update(task_id, status="failed", error=message, finished_at=datetime.now(timezone.utc))
        finally:
            video_path.unlink(missing_ok=True)
            audio_path.unlink(missing_ok=True)
            self._paths.pop(task_id, None)

    def get(self, task_id: str) -> PracticeTask:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise TaskNotFoundError(task_id)
            return task.model_copy(deep=True)
