"""用户端的媒体适配层，音频模块依然只接收音频。

复用项目已有 PyAV，流式解码第一条音轨为 16 kHz 单声道 WAV。
这里不分析表情、动作或画面；后续视频评价模块可独立接入。
"""

from __future__ import annotations

import wave
from pathlib import Path

import av

VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}


class MediaError(ValueError):
    pass


def extract_audio(video_path: Path, audio_path: Path, max_seconds: int) -> float:
    """Return the start of the extracted WAV on the recording's playback timeline."""
    samples = 0
    first_sample_pts = None
    audio_offset = 0.0
    try:
        with av.open(str(video_path)) as container, wave.open(str(audio_path), "wb") as output:
            if not container.streams.video:
                raise MediaError("文件中没有视频画面，请上传讲解视频。")
            if not container.streams.audio:
                raise MediaError("视频没有音轨，请选择带声音的讲解视频。")
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(16000)
            resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)

            def write_frames(frames: list) -> None:
                nonlocal samples, first_sample_pts, audio_offset
                for frame in frames:
                    # Positions are in PCM samples. Keep timestamp gaps in the WAV so
                    # Whisper, pause detection and the video share a playback timeline.
                    if frame.pts is not None and frame.time_base is not None:
                        pts = round(frame.pts * frame.time_base * 16000)
                        if first_sample_pts is None:
                            first_sample_pts = pts - samples
                            origin = (container.start_time or 0) / av.time_base
                            audio_offset = first_sample_pts / 16000 - origin
                        position = pts - first_sample_pts
                    else:
                        position = samples
                    if position + frame.samples > max_seconds * 16000:
                        raise MediaError(f"视频音轨超过 {max_seconds // 60} 分钟，请剪短后重试。")
                    if position > samples:
                        output.writeframesraw(bytes((position - samples) * 2))
                        samples = position
                    overlap = max(0, samples - position)
                    if overlap < frame.samples:
                        output.writeframesraw(frame.to_ndarray().tobytes()[overlap * 2:])
                        samples += frame.samples - overlap

            for frame in container.decode(container.streams.audio[0]):
                write_frames(resampler.resample(frame))
            write_frames(resampler.resample(None))
            if samples == 0:
                raise MediaError("视频音轨为空，请确认录制时已开启麦克风。")
            return audio_offset
    except MediaError:
        audio_path.unlink(missing_ok=True)
        raise
    except (av.error.FFmpegError, ValueError, OSError) as exc:
        audio_path.unlink(missing_ok=True)
        raise MediaError("无法读取这个视频，请尝试重新导出为 MP4 后上传。") from exc
