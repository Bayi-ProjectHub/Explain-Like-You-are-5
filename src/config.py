"""项目运行配置。

所有配置都从环境变量读取，默认值只覆盖本地开发的常见情况；
部署时不需要改代码，改环境变量即可。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# 项目根目录（本文件位于 src/ 下）
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    """转写与上传相关的配置。"""

    # faster-whisper 模型大小：tiny / base / small / medium / large-v3
    whisper_model: str
    # 本机无 GPU，固定 cpu；以后换 GPU 机器可改成 cuda
    whisper_device: str
    # int8 量化是 CPU 上速度与精度的折中
    whisper_compute_type: str
    # 上传音频的临时目录，转写完成后即删除文件
    upload_dir: Path
    # 单次上传大小上限（MB）
    max_upload_mb: int
    # 用户端视频的音轨时长上限，默认 10 分钟
    max_video_seconds: int = 600
    video_model_path: Path | None = None
    delivery_report_enabled: bool = False


def load_settings() -> Settings:
    video_model_path = os.environ.get("VIDEO_MODEL_PATH")
    return Settings(
        whisper_model=_env("WHISPER_MODEL", "small"),
        whisper_device=_env("WHISPER_DEVICE", "cpu"),
        whisper_compute_type=_env("WHISPER_COMPUTE_TYPE", "int8"),
        upload_dir=Path(_env("UPLOAD_DIR", str(PROJECT_ROOT / "data" / "uploads"))),
        max_upload_mb=int(_env("MAX_UPLOAD_MB", "200")),
        max_video_seconds=int(_env("MAX_VIDEO_SECONDS", "600")),
        video_model_path=Path(video_model_path) if video_model_path else None,
        delivery_report_enabled=_env("DELIVERY_REPORT_ENABLED", "false").lower() in {"true", "1"},
    )
