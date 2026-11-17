
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .audio.engine import FasterWhisperTranscriber
from .audio.router import router as audio_router
from .audio.service import TranscriptionService
from .evaluation.router import router as evaluation_router
from .config import PROJECT_ROOT, load_settings
from .delivery.report import DeliveryReporter
from .practice.router import router as practice_router
from .practice.service import PracticeService
from .practice.vocabulary import load_vocabulary

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时装配依赖。模型本身在第一次转写时才加载，所以启动很快。"""
    settings = load_settings()
    transcriber = FasterWhisperTranscriber(
        model_size=settings.whisper_model,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
    )
    app.state.transcription_service = TranscriptionService(
        transcriber=transcriber,
        upload_dir=settings.upload_dir,
        max_upload_mb=settings.max_upload_mb,
    )
    load_vocabulary()  # 启动时验证词库，错误尽早暴露。
    app.state.practice_service = PracticeService(
        app.state.transcription_service, settings.upload_dir / "practice",
        settings.max_upload_mb, settings.max_video_seconds,
        video_model_path=settings.video_model_path,
        reporter=DeliveryReporter() if settings.delivery_report_enabled else None,
    )
    logger.info("音频转写模块就绪（模型 %s）", settings.whisper_model)
    yield


app = FastAPI(
    title="Explain Like You're 5",
    description="Backend API for ELY5",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(audio_router)
app.include_router(evaluation_router)
app.include_router(practice_router)
app.mount("/app", StaticFiles(directory=PROJECT_ROOT / "web", html=True), name="product")


@app.get("/app", include_in_schema=False)
async def product():
    return RedirectResponse("/app/")


@app.get("/")
async def root():
    return {
        "message": "Welcome to Explain Like You're 5!",
        "status": "running",
    }
