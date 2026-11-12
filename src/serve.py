from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI

from .audio.engine import FasterWhisperTranscriber
from .audio.router import router as audio_router
from .audio.service import TranscriptionService
from .config import load_settings

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
    logger.info("音频转写模块就绪（模型 %s）", settings.whisper_model)
    yield


app = FastAPI(
    title="Explain Like You're 5",
    description="Backend API for ELY5",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(audio_router)


@app.get("/")
async def root():
    return {
        "message": "Welcome to Explain Like You're 5!",
        "status": "running",
    }
