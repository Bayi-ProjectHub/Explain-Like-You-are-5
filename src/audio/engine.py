"""转写引擎。

引擎只负责「音频文件 -> 转写结果」，不依赖 FastAPI。
以后若要换云端服务，实现同样的 Transcriber 协议即可，其余代码不用动。
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Protocol

from .schemas import Segment, TranscriptionResult

logger = logging.getLogger(__name__)


class Transcriber(Protocol):
    """转写引擎的接口。"""

    def transcribe(self, audio_path: Path, language: str | None = None) -> TranscriptionResult:
        """把音频文件转写成文本，language 为 None 时自动识别语言。"""
        ...


class FasterWhisperTranscriber:
    """本地 faster-whisper 推理。

    模型在第一次转写时才加载，避免开发服务器启动时就要等模型下载/初始化。
    """

    def __init__(self, model_size: str, device: str, compute_type: str) -> None:
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._model = None
        self._lock = threading.Lock()

    def _load_model(self):
        # 延迟导入：只测接口的测试不需要真正加载模型
        from faster_whisper import WhisperModel

        logger.info(
            "加载 faster-whisper 模型 size=%s device=%s compute_type=%s",
            self._model_size,
            self._device,
            self._compute_type,
        )
        return WhisperModel(
            self._model_size,
            device=self._device,
            compute_type=self._compute_type,
        )

    def transcribe(self, audio_path: Path, language: str | None = None) -> TranscriptionResult:
        # 模型加载较慢，用锁保证并发请求下只加载一次
        if self._model is None:
            with self._lock:
                if self._model is None:
                    self._model = self._load_model()

        segment_iter, info = self._model.transcribe(
            str(audio_path),
            language=language,
            vad_filter=True,
        )
        raw_segments = list(segment_iter)
        segments = [
            Segment(
                id=index,
                start=round(segment.start, 2),
                end=round(segment.end, 2),
                text=segment.text.strip(),
            )
            for index, segment in enumerate(raw_segments)
        ]
        # 英文分句文本通常以空格开头，拼接原始文本（不要先 strip）再整体 strip，
        # 否则会丢掉分句之间的空格，出现 "have.As" 这类粘连。
        text = "".join(segment.text for segment in raw_segments).strip()
        return TranscriptionResult(
            text=text,
            language=info.language,
            language_probability=info.language_probability,
            duration=round(info.duration, 2) if info.duration is not None else None,
            segments=segments,
        )
