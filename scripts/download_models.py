"""下载画面分析使用的 MediaPipe 模型。

默认只下载 Holistic（画面分析必需）；--all 还会下载专用 Face、Pose Heavy
和 Hand 模型，它们在关键点缺失时作为回退检测器。已存在的文件默认跳过。
"""

from __future__ import annotations

import argparse
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODEL_DIR = PROJECT_ROOT / "data" / "models"
MODEL_BASE_URL = "https://storage.googleapis.com/mediapipe-models"

# 文件名由分析代码直接查找，不能随意改动。
MODELS = {
    "holistic_landmarker.task": "holistic_landmarker/holistic_landmarker",
    "face_landmarker.task": "face_landmarker/face_landmarker",
    "pose_landmarker_heavy.task": "pose_landmarker/pose_landmarker_heavy",
    "hand_landmarker.task": "hand_landmarker/hand_landmarker",
}
REQUIRED_MODEL = "holistic_landmarker.task"


def download(name: str, *, force: bool) -> None:
    destination = MODEL_DIR / name
    if destination.is_file() and not force:
        print(f"跳过 {name}（已存在）")
        return

    url = f"{MODEL_BASE_URL}/{MODELS[name]}/float16/1/{name}"
    print(f"下载 {name} …")
    try:
        with urllib.request.urlopen(url, timeout=60) as response, destination.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
    except (OSError, urllib.error.URLError) as exc:
        # 不留下下载到一半的文件，否则下次会被误判为已存在。
        destination.unlink(missing_ok=True)
        raise SystemExit(f"下载 {name} 失败：{exc}") from exc
    print(f"已保存 {destination.relative_to(PROJECT_ROOT).as_posix()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="下载 MediaPipe 画面分析模型。")
    parser.add_argument("--all", action="store_true", help="同时下载专用 Face、Pose Heavy 和 Hand 模型")
    parser.add_argument("--force", action="store_true", help="覆盖已存在的文件")
    args = parser.parse_args()

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    names = list(MODELS) if args.all else [REQUIRED_MODEL]
    for name in names:
        download(name, force=args.force)

    model_path = (MODEL_DIR / REQUIRED_MODEL).relative_to(PROJECT_ROOT).as_posix()
    print(f"\n在 .env 中设置 VIDEO_MODEL_PATH={model_path}")


if __name__ == "__main__":
    main()
