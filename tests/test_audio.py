"""音频转写接口的单元测试。

用假引擎代替真实模型，测试只覆盖上传、任务状态流转和错误处理，不下载模型。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.audio.router import router
from src.audio.schemas import Segment, TranscriptionResult
from src.audio.service import TranscriptionService


class FakeTranscriber:
    """记录调用参数，返回固定结果的假引擎。"""

    def __init__(self, result: TranscriptionResult | None = None, error: Exception | None = None) -> None:
        self.result = result or TranscriptionResult(
            text="大家好，今天讲什么是熵。",
            language="zh",
            language_probability=0.98,
            duration=3.5,
            segments=[
                Segment(id=0, start=0.0, end=1.5, text="大家好，"),
                Segment(id=1, start=1.5, end=3.5, text="今天讲什么是熵。"),
            ],
        )
        self.error = error
        self.calls: list[tuple[Path, str | None]] = []

    def transcribe(self, audio_path: Path, language: str | None = None) -> TranscriptionResult:
        # 转写时文件必须还在，说明服务没有提前删除上传文件
        assert audio_path.exists(), "转写时音频文件已被删除"
        self.calls.append((audio_path, language))
        if self.error is not None:
            raise self.error
        return self.result


def make_client(transcriber: FakeTranscriber, upload_dir: Path, max_upload_mb: int = 1) -> TestClient:
    service = TranscriptionService(transcriber, upload_dir, max_upload_mb)
    app = FastAPI()
    app.include_router(router)
    app.state.transcription_service = service
    return TestClient(app)


def test_upload_and_poll_transcription(tmp_path: Path) -> None:
    transcriber = FakeTranscriber()
    client = make_client(transcriber, tmp_path)

    response = client.post(
        "/audio/transcriptions",
        files={"file": ("demo.wav", b"fake audio bytes", "audio/wav")},
    )
    assert response.status_code == 202
    created = response.json()
    assert created["status"] == "queued"
    assert created["result"] is None
    task_id = created["task_id"]

    # TestClient 会等后台任务执行完，此时已经是 completed
    polled = client.get(f"/audio/transcriptions/{task_id}")
    assert polled.status_code == 200
    body = polled.json()
    assert body["status"] == "completed"
    assert body["result"]["text"] == "大家好，今天讲什么是熵。"
    assert body["result"]["language"] == "zh"
    assert len(body["result"]["segments"]) == 2
    assert body["result"]["segments"][1]["start"] == 1.5
    assert body["finished_at"] is not None

    # 转写完成后临时音频被删除
    assert len(transcriber.calls) == 1
    audio_path, language = transcriber.calls[0]
    assert language is None
    assert not audio_path.exists()


def test_language_is_passed_to_engine(tmp_path: Path) -> None:
    transcriber = FakeTranscriber()
    client = make_client(transcriber, tmp_path)

    response = client.post(
        "/audio/transcriptions",
        files={"file": ("demo.mp3", b"fake audio bytes", "audio/mpeg")},
        data={"language": "zh"},
    )
    assert response.status_code == 202
    assert transcriber.calls[0][1] == "zh"


def test_unknown_task_returns_404(tmp_path: Path) -> None:
    client = make_client(FakeTranscriber(), tmp_path)
    response = client.get("/audio/transcriptions/not-a-task")
    assert response.status_code == 404


def test_unsupported_format_returns_415(tmp_path: Path) -> None:
    client = make_client(FakeTranscriber(), tmp_path)
    response = client.post(
        "/audio/transcriptions",
        files={"file": ("notes.txt", b"not audio", "text/plain")},
    )
    assert response.status_code == 415


def test_too_large_upload_returns_413(tmp_path: Path) -> None:
    client = make_client(FakeTranscriber(), tmp_path, max_upload_mb=1)
    big_payload = b"x" * (1024 * 1024 + 1)
    response = client.post(
        "/audio/transcriptions",
        files={"file": ("big.wav", big_payload, "audio/wav")},
    )
    assert response.status_code == 413


def test_failed_transcription_is_reported(tmp_path: Path) -> None:
    client = make_client(FakeTranscriber(error=RuntimeError("模型加载失败")), tmp_path)

    response = client.post(
        "/audio/transcriptions",
        files={"file": ("demo.wav", b"fake audio bytes", "audio/wav")},
    )
    task_id = response.json()["task_id"]

    body = client.get(f"/audio/transcriptions/{task_id}").json()
    assert body["status"] == "failed"
    assert "RuntimeError" in body["error"]
    assert "模型加载失败" in body["error"]
