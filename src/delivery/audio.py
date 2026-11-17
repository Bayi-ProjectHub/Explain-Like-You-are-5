"""Find sustained quiet intervals in the same PCM audio used for transcription."""

import wave
from pathlib import Path
import re

import numpy as np

from .schemas import Evidence
from ..audio.schemas import TranscriptionResult


def analyze_audio(path: Path, offset: float, transcript: TranscriptionResult) -> list[Evidence]:
    observations = quiet_intervals(path, offset)
    rates = []
    for segment in transcript.segments:
        duration = segment.end - segment.start
        if duration < 2:
            continue
        # Count Han characters and Latin words separately in mixed-language speech.
        han = len(re.findall(r"[\u3400-\u9fff]", segment.text))
        words = len(re.findall(r"[A-Za-z]+(?:['’][A-Za-z]+)*", segment.text))
        metrics = {}
        if han:
            metrics["han_characters_per_minute"] = round(60 * han / duration)
        if words:
            metrics["latin_words_per_minute"] = round(60 * words / duration)
        if metrics:
            rates.append((segment.start, segment.end, metrics))
    if len(rates) > 8:
        rates = [rates[round(index * (len(rates) - 1) / 7)] for index in range(8)]
    observations.extend((start + offset, end + offset, metrics) for start, end, metrics in rates)
    observations.sort(key=lambda item: item[0])
    return [Evidence(id=f"A{i}", start=round(start, 3), end=round(end, 3), metrics=metrics)
            for i, (start, end, metrics) in enumerate(observations, 1)]


def quiet_intervals(path: Path, offset: float) -> list[tuple[float, float, dict[str, float]]]:
    with wave.open(str(path), "rb") as source:
        rate = source.getframerate()
        samples = np.frombuffer(source.readframes(source.getnframes()), dtype="<i2")
    size = rate // 20  # 50 ms windows; the practice extractor always writes 16 kHz mono PCM.
    if len(samples) < size:
        return []
    frames = samples[: len(samples) // size * size].reshape(-1, size).astype(np.float32)
    rms = np.sqrt(np.mean(frames ** 2, axis=1))
    # Skip digital silence and report relative quiet between loud regions. This is
    # an energy measurement, so background noise may mask pauses.
    reference = float(np.percentile(rms, 90))
    if reference < 32:
        return []
    loud = np.flatnonzero(rms > max(32, reference * 0.10))
    if len(loud) < 2:
        return []
    intervals = [(int(a) + 1, int(b)) for a, b in zip(loud, loud[1:]) if b - a >= 13]
    # Keep the longest pauses first, then put them back in playback order.
    intervals = sorted(sorted(intervals, key=lambda p: p[1] - p[0], reverse=True)[:12])
    return [(offset + a / 20, offset + b / 20, {"quiet_seconds": round((b - a) / 20, 3)})
            for a, b in intervals]
