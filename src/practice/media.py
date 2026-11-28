"""用户端的媒体适配层，音频模块依然只接收音频。

复用项目已有 PyAV，流式解码第一条音轨为 16 kHz 单声道 WAV。
这里不分析表情、动作或画面；后续视频评价模块可独立接入。
"""

from __future__ import annotations

import wave
from pathlib import Path

import av


class MediaError(ValueError):
    pass


def extract_audio(video_path: Path, audio_path: Path, max_seconds: int) -> None:
    samples = 0
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
                nonlocal samples
                for frame in frames:
                    samples += frame.samples
                    if samples > max_seconds * 16000:
                        raise MediaError(f"视频音轨超过 {max_seconds // 60} 分钟，请剪短后重试。")
                    output.writeframes(frame.to_ndarray().tobytes())

            for frame in container.decode(container.streams.audio[0]):
                write_frames(resampler.resample(frame))
            write_frames(resampler.resample(None))
            if samples == 0:
                raise MediaError("视频音轨为空，请确认录制时已开启麦克风。")
    except MediaError:
        audio_path.unlink(missing_ok=True)
        raise
    except (av.error.FFmpegError, ValueError, OSError) as exc:
        audio_path.unlink(missing_ok=True)
        raise MediaError("无法读取这个视频，请尝试重新导出为 MP4 后上传。") from exc
