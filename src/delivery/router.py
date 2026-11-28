"""Run video analysis by itself and return the visual evidence."""

import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated

from av.error import FFmpegError
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from ..config import Settings, load_settings
from .schemas import VisualEvidence, parse_presenter_ranges
from .upload import VideoTooLargeError, VideoUploadError, save_video_upload
from .video import VideoReadError, analyze_video

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/video", tags=["video"])


@router.post(
    "/analyses",
    response_model=VisualEvidence,
    summary="单独分析视频画面",
    responses={
        413: {"description": "文件超过上传大小上限"},
        415: {"description": "文件格式不支持或文件为空"},
        422: {"description": "讲者时段不正确或无法读取视频画面"},
        500: {"description": "画面分析失败"},
        503: {"description": "视频模型或依赖未配置"},
    },
)
def analyze_video_upload(
    file: Annotated[UploadFile, File(description="讲解视频，可以没有音轨。")],
    settings: Annotated[Settings, Depends(load_settings)],
    presenter_ranges: Annotated[str, Form(
        max_length=12000,
        description='可选的讲者出镜时段，按播放器的秒数填写，如 [{"start": 5, "end": 28}]。',
    )] = "[]",
) -> VisualEvidence:
    """上传视频后等待分析结果。只读取画面，支持无声视频。"""
    try:
        ranges = parse_presenter_ranges(presenter_ranges)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    model_path = settings.video_model_path
    if model_path is None or not model_path.is_file():
        raise HTTPException(status_code=503, detail="视频模型文件未找到，请检查 VIDEO_MODEL_PATH。")

    try:
        # FastAPI 在工作线程中运行同步路由，临时文件留到分析结束再删除。
        with TemporaryDirectory(prefix="video-analysis-", dir=settings.upload_dir) as directory:
            path = save_video_upload(file, Path(directory), "video", settings.max_upload_mb * 1024 * 1024)
            return analyze_video(path, model_path, settings.max_video_seconds, ranges)
    except VideoTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except VideoUploadError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except VideoReadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FFmpegError as exc:
        raise HTTPException(status_code=422, detail="无法读取这个视频，请尝试重新导出为 MP4 后上传。") from exc
    except Exception as exc:
        if isinstance(exc, ModuleNotFoundError) and exc.name == "mediapipe":
            raise HTTPException(status_code=503, detail="缺少 MediaPipe，请安装项目的 video 依赖。") from exc
        logger.exception("独立视频分析失败")
        raise HTTPException(status_code=500, detail="画面分析失败，请查看服务端日志。") from exc
