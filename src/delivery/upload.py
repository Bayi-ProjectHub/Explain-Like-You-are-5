"""Save a bounded video upload for either analysis entry point."""

from pathlib import Path

from fastapi import UploadFile

VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}


class VideoUploadError(ValueError):
    """The file extension is unsupported or the upload is empty."""


class VideoTooLargeError(VideoUploadError):
    """The upload exceeds the configured size limit."""


def save_video_upload(file: UploadFile, directory: Path, file_id: str, max_bytes: int) -> Path:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in VIDEO_SUFFIXES:
        raise VideoUploadError("请选择 MP4、MOV、WebM、MKV 或 M4V 视频。")

    path = directory / f"{file_id}{suffix}"
    written = 0
    try:
        with path.open("wb") as output:
            while chunk := file.file.read(1024 * 1024):
                written += len(chunk)
                if written > max_bytes:
                    raise VideoTooLargeError(f"视频超过 {max_bytes // (1024 * 1024)} MB 上限。")
                output.write(chunk)
        if not written:
            raise VideoUploadError("视频文件为空，请重新选择。")
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path
