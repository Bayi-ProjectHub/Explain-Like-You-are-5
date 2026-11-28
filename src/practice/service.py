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
from starlette.concurrency import run_in_threadpool

from ..audio.schemas import TaskStatus, TranscriptionResult
from ..audio.service import AudioTooLargeError, TaskNotFoundError, TranscriptionService
from ..delivery.audio import analyze_audio
from ..delivery.clock import audio_playback_offset
from ..delivery.report import build_delivery_report
from ..delivery.schemas import DeliveryEvidence, DeliveryReport, PlaybackRange
from ..delivery.upload import VideoTooLargeError, VideoUploadError, save_video_upload
from ..delivery.video import analyze_video
from .media import MediaError, extract_audio
from .vocabulary import Language, Term

logger = logging.getLogger(__name__)


class ModuleState(BaseModel):
    status: Literal["completed", "pending", "failed", "insufficient_evidence"]
    message: str


class PracticeTask(BaseModel):
    task_id: str
    status: Literal["queued", "extracting", "transcribing", "analyzing_delivery", "completed", "failed"]
    created_at: datetime
    finished_at: datetime | None = None
    term: Term
    language: Language
    filename: str
    presenter_ranges: list[PlaybackRange] = Field(default_factory=list)
    result: TranscriptionResult | None = None
    modules: dict[str, ModuleState] = Field(default_factory=dict)
    delivery_evidence: DeliveryEvidence | None = None
    delivery_report: DeliveryReport | None = None
    error: str | None = None


class PracticeService:
    def __init__(
        self, transcription_service: TranscriptionService, upload_dir: Path,
        max_upload_mb: int, max_video_seconds: int = 600,
        video_model_path: Path | None = None,
    ) -> None:
        self._audio = transcription_service
        self._upload_dir = upload_dir
        self._max_bytes = max_upload_mb * 1024 * 1024
        self._max_seconds = max_video_seconds
        self._video_model_path = video_model_path
        self._tasks: dict[str, PracticeTask] = {}
        self._paths: dict[str, Path] = {}
        self._lock = threading.Lock()
        # 当前本地模型适合单个练习逐个处理，避免多个视频同时占满内存。
        self._worker = asyncio.Lock()
        upload_dir.mkdir(parents=True, exist_ok=True)

    async def submit(self, file: UploadFile, term: Term, language: Language,
                     presenter_ranges: list[PlaybackRange] | None = None) -> PracticeTask:
        task_id = uuid.uuid4().hex
        try:
            path = await run_in_threadpool(save_video_upload, file, self._upload_dir, task_id, self._max_bytes)
        except VideoTooLargeError as exc:
            raise AudioTooLargeError(str(exc)) from exc
        except VideoUploadError as exc:
            raise MediaError(str(exc)) from exc
        task = PracticeTask(
            task_id=task_id, status="queued", created_at=datetime.now(timezone.utc),
            term=term, language=language, filename=Path(file.filename or "video").name,
            presenter_ranges=presenter_ranges or [],
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
                audio_offset = await asyncio.to_thread(audio_playback_offset, video_path)
                self._update(task_id, status="transcribing")
                task = self.get(task_id)
                with audio_path.open("rb") as audio_file:
                    upload = UploadFile(filename="extracted.wav", file=audio_file)
                    transcription = await self._audio.submit(upload, language=task.language)
                await asyncio.to_thread(self._audio.process, transcription.task_id, task.language)
                completed = self._audio.get(transcription.task_id)
                if completed.status != TaskStatus.COMPLETED or completed.result is None:
                    raise MediaError("语音转写失败，请稍后重试；如持续失败，请检查服务端模型配置。")
                if not completed.result.text.strip():
                    raise MediaError("没有识别到讲话，请检查音量和麦克风后重试。")
                await self._analyze_delivery(task, video_path, audio_path, audio_offset, completed.result)
        except Exception as exc:
            logger.exception("练习任务 %s 失败", task_id)
            message = str(exc) if isinstance(exc, MediaError) else "处理遇到问题，请稍后重试。"
            self._update(task_id, status="failed", error=message, finished_at=datetime.now(timezone.utc))
        finally:
            video_path.unlink(missing_ok=True)
            audio_path.unlink(missing_ok=True)
            self._paths.pop(task_id, None)

    async def _analyze_delivery(self, task: PracticeTask, video_path: Path, audio_path: Path,
                                offset: float, transcript: TranscriptionResult) -> None:
        modules = {
            "transcription": ModuleState(status="completed", message="音轨提取与语音转写已完成"),
            "text_evaluation": ModuleState(status="pending", message="独立文本评分尚未接入练习"),
            "video_evaluation": ModuleState(status="pending", message="服务未配置视觉模型"),
        }
        evidence = DeliveryEvidence(audio_offset_seconds=round(offset, 6))
        self._update(task.task_id, status="analyzing_delivery", result=transcript)
        try:
            evidence.audio, evidence.audio_levels = await asyncio.to_thread(analyze_audio, audio_path, transcript)
            modules["audio_evidence"] = (
                ModuleState(status="completed", message="声音证据已提取") if evidence.audio_levels else
                ModuleState(status="insufficient_evidence", message="本次音轨的节奏证据不足")
            )
        except Exception:
            logger.exception("练习任务 %s 声音分析失败", task.task_id)
            modules["audio_evidence"] = ModuleState(status="failed", message="声音证据提取失败")

        if self._video_model_path is not None:
            try:
                evidence.visual = await asyncio.to_thread(
                    analyze_video, video_path, self._video_model_path, self._max_seconds, task.presenter_ranges,
                )
                modules["video_evaluation"] = (
                    ModuleState(status="completed", message="视觉证据已提取") if evidence.visual.windows or evidence.visual.events else
                    ModuleState(status="insufficient_evidence", message="画面中没有足够可见的特征")
                )
            except Exception:
                logger.exception("练习任务 %s 画面分析失败", task.task_id)
                modules["video_evaluation"] = ModuleState(status="failed", message="画面分析失败")

        report = build_delivery_report(evidence, transcript)
        modules["delivery_report"] = ModuleState(status="completed", message="本地视频报告已生成")
        self._update(task.task_id, status="completed", finished_at=datetime.now(timezone.utc),
                     modules=modules, delivery_evidence=evidence, delivery_report=report)

    def get(self, task_id: str) -> PracticeTask:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise TaskNotFoundError(task_id)
            return task.model_copy(deep=True)
