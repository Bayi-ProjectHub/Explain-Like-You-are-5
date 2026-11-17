"""用户端接口和真实媒体适配测试；假转写引擎不会下载模型。"""

from __future__ import annotations

from io import BytesIO
from fractions import Fraction
from pathlib import Path
from contextlib import contextmanager
from types import SimpleNamespace
import json

import av
import numpy as np
import pytest
from fastapi.testclient import TestClient

from src.audio.schemas import Segment, TranscriptionResult
from src.audio.service import TranscriptionService
from src.delivery.report import DeliveryReporter
from src.delivery.schemas import DIMENSIONS, Evidence, VisualEvidence
from src.practice.media import MediaError, extract_audio
from src.practice.service import PracticeService
from src.practice.vocabulary import load_vocabulary
from src.serve import app


class RecordingTranscriber:
    def __init__(self, error: bool = False, empty: bool = False):
        self.calls = []
        self.error = error
        self.empty = empty

    def transcribe(self, audio_path: Path, language=None):
        import wave

        with wave.open(str(audio_path)) as audio:
            assert audio.getframerate() == 16000
            assert audio.getnchannels() == 1
            assert audio.getnframes() == 16000
        self.calls.append(language)
        if self.error:
            raise RuntimeError("fake model failure")
        text = "" if self.empty else "A measure can become a target."
        return TranscriptionResult(
            text=text, language=language, duration=1,
            segments=[] if self.empty else [Segment(id=0, start=0, end=1, text=text)],
        )


def make_video(*, with_audio=True, with_video=True, with_voice=False, audio_start=0) -> bytes:
    """用已有 PyAV 生成 1 秒媒体，无需安装独立 ffmpeg。"""
    output = BytesIO()
    with av.open(output, mode="w", format="matroska") as container:
        if with_video:
            video = container.add_stream("ffv1", rate=25)
            video.width, video.height, video.pix_fmt = 16, 16, "yuv420p"
        if with_audio:
            audio = container.add_stream("pcm_s16le", rate=16000)
            audio.layout = "mono"
        # 所有流必须在第一次 mux（写入容器头）之前注册。
        if with_video:
            for index in range(25):
                frame = av.VideoFrame.from_ndarray(np.zeros((16, 16, 3), dtype=np.uint8), format="rgb24")
                frame.pts = index
                frame.time_base = Fraction(1, 25)
                for packet in video.encode(frame):
                    container.mux(packet)
            for packet in video.encode(None):
                container.mux(packet)
        if with_audio:
            samples = np.zeros((1, 16000), dtype=np.int16)
            if with_voice:
                samples[:, :3200] = 8000
                samples[:, -3200:] = 8000
            frame = av.AudioFrame.from_ndarray(samples, format="s16", layout="mono")
            frame.sample_rate = 16000
            frame.pts = audio_start
            frame.time_base = Fraction(1, 16000)
            for packet in audio.encode(frame):
                container.mux(packet)
            for packet in audio.encode(None):
                container.mux(packet)
    return output.getvalue()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    with TestClient(app) as client:
        engine = RecordingTranscriber()
        audio = TranscriptionService(engine, tmp_path / "audio", 1)
        app.state.practice_service = PracticeService(audio, tmp_path / "practice", 1)
        client.engine = engine
        yield client


def submit(client, payload=None, **data):
    return client.post(
        "/practice/submissions",
        data={"term_id": "goodharts-law", "language": "en", **data},
        files={"file": ("talk.mkv", make_video() if payload is None else payload, "video/x-matroska")},
    )


def test_vocabulary_is_bilingual_and_all_filter_combinations_have_alternatives(client):
    catalog = load_vocabulary()
    assert len(catalog.terms) == 36
    assert len(catalog.categories) == 6
    for category in catalog.categories:
        for difficulty in ("starter", "intermediate", "advanced"):
            terms = client.get("/practice/vocabulary", params={"category": category, "difficulty": difficulty}).json()["terms"]
            assert len(terms) == 2
            for term in terms:
                assert all(term["title"][lang] and term["prompt"][lang] for lang in ("zh", "en"))
            picked = client.get("/practice/terms/random", params={"category": category, "difficulty": difficulty, "exclude_id": terms[0]["id"]}).json()
            assert picked["id"] == terms[1]["id"]


def test_invalid_filter_and_no_matches(client):
    assert client.get("/practice/terms/random?difficulty=impossible").status_code == 422
    assert client.get("/practice/terms/random?category=missing").status_code == 404


@pytest.mark.parametrize("language", ["zh", "en"])
def test_video_to_transcript_pipeline(client, tmp_path, language):
    response = submit(client, language=language)
    assert response.status_code == 202
    created = response.json()
    assert created["status"] == "queued"
    assert created["result"] is None
    task = client.get(f"/practice/submissions/{created['task_id']}").json()
    assert task["status"] == "completed"
    assert task["term"]["id"] == "goodharts-law"
    assert task["language"] == language
    assert task["result"]["text"] == "A measure can become a target."
    assert task["modules"]["transcription"]["status"] == "completed"
    assert task["modules"]["text_evaluation"]["status"] == "pending"
    assert task["modules"]["video_evaluation"]["status"] == "pending"
    assert task["finished_at"]
    assert client.engine.calls == [language]
    assert not list(tmp_path.rglob("*.mkv"))
    assert not list(tmp_path.rglob("*.wav"))


@pytest.mark.parametrize("payload", [b"broken video", make_video(with_audio=False), make_video(with_video=False)])
def test_bad_media_fails_with_recoverable_error_and_cleans_up(client, tmp_path, payload):
    response = submit(client, payload)
    task = client.get(f"/practice/submissions/{response.json()['task_id']}").json()
    assert task["status"] == "failed"
    assert task["error"]
    assert task["result"] is None
    assert not list(tmp_path.rglob("*.mkv"))
    assert not list(tmp_path.rglob("*.wav"))


def test_submission_validation(client, tmp_path):
    assert submit(client, term_id="unknown").status_code == 422
    assert submit(client, language="fr").status_code == 422
    assert submit(client, b"").status_code == 415
    assert submit(client, b"x" * (1024 * 1024 + 1)).status_code == 413
    assert client.post("/practice/submissions", data={"term_id": "gravity", "language": "zh"}, files={"file": ("a.txt", b"hi")}).status_code == 415
    assert client.get("/practice/submissions/missing").status_code == 404
    assert not list(tmp_path.rglob("*.mkv"))


@pytest.mark.parametrize("empty", [True, False])
def test_transcription_failure_is_not_reported_as_success(client, tmp_path, empty):
    client.engine.error = not empty
    client.engine.empty = empty
    response = submit(client)
    task = client.get(f"/practice/submissions/{response.json()['task_id']}").json()
    assert task["status"] == "failed"
    assert task["result"] is None
    assert task["error"]
    assert not list(tmp_path.rglob("*.wav"))


def test_extraction_rejects_long_audio_and_deletes_partial_wav(tmp_path):
    video = tmp_path / "test.mkv"
    audio = tmp_path / "test.wav"
    video.write_bytes(make_video())
    with pytest.raises(MediaError):
        extract_audio(video, audio, max_seconds=0)
    assert not audio.exists()


def test_product_page_and_existing_root_remain_available(client):
    assert client.get("/").json()["status"] == "running"
    response = client.get("/app/")
    assert response.status_code == 200
    assert "讲解师" in response.text
    assert client.get("/app/app.js").status_code == 200
    assert client.get("/app/styles.css").status_code == 200


def test_extract_audio_reports_offset_in_original_playback(tmp_path):
    video, audio = tmp_path / "offset.mkv", tmp_path / "offset.wav"
    video.write_bytes(make_video(audio_start=4000))
    assert extract_audio(video, audio, max_seconds=2) == pytest.approx(0.25, abs=0.002)


@pytest.mark.parametrize("valid_citation", [True, False])
def test_delivery_report_combines_video_audio_and_transcript(client, tmp_path, monkeypatch, valid_citation):
    def visual_analysis(path, model_path, max_seconds):
        assert path.is_file()
        return VisualEvidence(sample_hz=6, coverage={"hands": 1}, windows=[
            Evidence(id="V1", start=0.1, end=0.95, metrics={"gesture_bursts": 1}),
        ])

    def complete(**options):
        payload = json.loads(options["messages"][1]["content"])
        assert payload["topic"] == "Goodhart’s law"
        assert [entry["id"] for entry in payload["evidence"]] == ["V1", "A1"]
        assert [entry["transcript_ids"] for entry in payload["evidence"]] == [[0], [0]]
        assert payload["evidence"][1]["metrics"]["quiet_seconds"] == 0.6
        citations = {"gesture": ["V1"], "voice": ["A1"], "structure": ["T0"],
                     "coordination": ["V1", "T0"] if valid_citation else ["V1", "T99"]}
        content = json.dumps({"summary": "Timeline feedback", "feedback": [
            {"dimension": name, "status": "observed" if name in citations else "insufficient_evidence",
             "evidence_ids": citations.get(name, []), "observation": "Observation" if name in citations else "",
             "suggestion": "Try it again" if name in citations else ""} for name in DIMENSIONS
        ]})
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    @contextmanager
    def cloud_client(**kwargs):
        assert kwargs["base_url"] == "https://api.deepseek.com"
        yield SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=complete)))

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr("src.practice.service.analyze_video", visual_analysis)
    monkeypatch.setattr("src.delivery.report.OpenAI", cloud_client)
    app.state.practice_service = PracticeService(
        TranscriptionService(client.engine, tmp_path / "audio", 1), tmp_path / "practice", 1,
        video_model_path=tmp_path / "test.task", reporter=DeliveryReporter(),
    )
    response = submit(client, make_video(with_voice=True))
    task = client.get(f"/practice/submissions/{response.json()['task_id']}").json()
    assert task["status"] == "completed"
    assert task["modules"]["video_evaluation"]["status"] == "completed"
    assert task["modules"]["audio_evidence"]["status"] == "completed"
    assert task["result"]["segments"][0]["id"] == 0
    if valid_citation:
        assert task["modules"]["delivery_report"]["status"] == "completed"
        assert len(task["delivery_report"]["feedback"]) == 7
    else:
        assert task["modules"]["delivery_report"]["status"] == "failed"
        assert task["delivery_report"] is None
    assert not list(tmp_path.rglob("*.mkv"))
    assert not list(tmp_path.rglob("*.wav"))


def test_vision_failure_preserves_audio_and_transcript(client, tmp_path, monkeypatch):
    def missing_model(*args):
        raise FileNotFoundError("test.task")

    monkeypatch.setattr("src.practice.service.analyze_video", missing_model)
    app.state.practice_service = PracticeService(
        TranscriptionService(client.engine, tmp_path / "audio", 1), tmp_path / "practice", 1,
        video_model_path=tmp_path / "test.task",
    )
    response = submit(client, make_video(with_voice=True))
    task = client.get(f"/practice/submissions/{response.json()['task_id']}").json()
    assert task["status"] == "completed"
    assert task["modules"]["video_evaluation"]["status"] == "failed"
    assert task["result"]["text"]
    assert task["delivery_evidence"]["visual"] is None
    assert task["delivery_evidence"]["audio"][0]["transcript_ids"] == [0]
