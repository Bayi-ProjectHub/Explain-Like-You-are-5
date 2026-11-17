"""转写引擎的单元测试。

用一个极简的假模型替身，不需要下载真实模型。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.audio.engine import FasterWhisperTranscriber


@dataclass
class _FakeSegment:
    start: float
    end: float
    text: str


@dataclass
class _FakeInfo:
    language: str
    language_probability: float
    duration: float


class _StubModel:
    """返回固定分句的假 WhisperModel，模拟 whisper 分句文本带前导空格的行为。"""

    def __init__(self, segments: list[_FakeSegment]) -> None:
        self._segments = segments

    def transcribe(self, audio_path, language=None, vad_filter=False):
        return iter(self._segments), _FakeInfo(
            language=language or "en",
            language_probability=0.99,
            duration=self._segments[-1].end if self._segments else 0.0,
        )


def test_transcribe_keeps_spaces_between_segments() -> None:
    transcriber = FasterWhisperTranscriber("tiny", "cpu", "int8")
    transcriber._model = _StubModel(
        [
            _FakeSegment(0.0, 2.0, " Hello world."),
            _FakeSegment(2.0, 4.0, " This is a test."),
        ]
    )

    result = transcriber.transcribe(Path("dummy.wav"))

    # 整段文本保留分句之间的空格
    assert result.text == "Hello world. This is a test."
    # 每个分句自身去掉首尾空格，时间戳保留两位小数
    assert [segment.text for segment in result.segments] == ["Hello world.", "This is a test."]
    assert result.segments[1].start == 2.0
    assert result.duration == 4.0
    assert result.language == "en"


def test_transcribe_handles_empty_segments() -> None:
    transcriber = FasterWhisperTranscriber("tiny", "cpu", "int8")
    transcriber._model = _StubModel([])

    result = transcriber.transcribe(Path("dummy.wav"), language="zh")

    assert result.text == ""
    assert result.segments == []
    assert result.language == "zh"
