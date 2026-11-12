"""集成测试：用真实 faster-whisper 模型转写一段公共音频。

默认跳过（需要下载模型，首次运行较慢）。需要真实模型时设置 ELY5_RUN_INTEGRATION=1 再运行：
    ELY5_RUN_INTEGRATION=1 uv run pytest -m integration -v
模型从 huggingface_hub 下载，网络受限时设置 HF_ENDPOINT 指向镜像。
"""

from __future__ import annotations

import os
import urllib.request
from pathlib import Path

import pytest

from src.audio.engine import FasterWhisperTranscriber

# conftest.py 依据这个标记在未设置 ELY5_RUN_INTEGRATION=1 时跳过本文件
pytestmark = pytest.mark.integration

# OpenAI whisper 仓库里的公共测试音频，内容是一段英文演讲
AUDIO_URL = "https://raw.githubusercontent.com/openai/whisper/main/tests/jfk.flac"


@pytest.fixture(scope="module")
def sample_audio(tmp_path_factory: pytest.TempPathFactory) -> Path:
    audio_path = tmp_path_factory.mktemp("audio") / "jfk.flac"
    urllib.request.urlretrieve(AUDIO_URL, audio_path)
    return audio_path


def test_transcribe_real_audio(sample_audio: Path) -> None:
    model_size = os.environ.get("ELY5_WHISPER_MODEL", "tiny")
    transcriber = FasterWhisperTranscriber(model_size, "cpu", "int8")

    result = transcriber.transcribe(sample_audio, language="en")

    assert "fellow americans" in result.text.lower()
    assert result.segments, "至少应产出一个分句"
    assert result.segments[0].start >= 0
    assert result.segments[-1].end <= result.duration + 1
