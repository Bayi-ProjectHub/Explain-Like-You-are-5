"""Find sustained quiet intervals in the same PCM audio used for transcription."""

import wave
from pathlib import Path
import re

import numpy as np

from .schemas import Evidence
from ..audio.schemas import TranscriptionResult


def analyze_audio(path: Path, transcript: TranscriptionResult) -> tuple[list[Evidence], list[Evidence]]:
    with wave.open(str(path), "rb") as source:
        rate = source.getframerate()
        samples = np.frombuffer(source.readframes(source.getnframes()), dtype="<i2")
    size = rate // 20  # 50 ms windows; practice always writes mono PCM at 16 kHz.
    frames = samples[: len(samples) // size * size].reshape(-1, size).astype(np.float32)
    rms = np.sqrt(np.mean(frames ** 2, axis=1))
    observations = quiet_intervals(rms)
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
    observations.extend(rates)
    observations.sort(key=lambda item: item[0])
    entries = [Evidence(id=f"A{i}", start=round(start, 3), end=round(end, 3), metrics=metrics)
               for i, (start, end, metrics) in enumerate(observations, 1)]
    levels = []
    for i, start in enumerate(range(0, len(samples), rate * 2), 1):
        stop = min(start + rate * 2, len(samples))
        audio = samples[start:stop].astype(np.float32) / 32768.0
        level = round(float(20 * np.log10(max(1e-5, np.sqrt(np.mean(audio ** 2))))), 2)
        levels.append(Evidence(id=f"L{i}", start=start / rate, end=stop / rate,
                               metrics={"rms_dbfs": level}))
    return entries, levels


def quiet_intervals(rms: np.ndarray) -> list[tuple[float, float, dict[str, float]]]:
    if not len(rms):
        return []
    # Skip digital silence and report relative quiet between loud regions. This is
    # an energy measurement, so background noise may mask pauses.
    reference = float(np.percentile(rms, 90))
    if reference < 32:
        return []
    loud = np.flatnonzero(rms > max(32, reference * 0.10))
    if len(loud) < 2:
        return []
    intervals = [(int(a) + 1, int(b)) for a, b in zip(loud, loud[1:]) if b - a >= 13]
    return [(a / 20, b / 20, {"quiet_seconds": round((b - a) / 20, 3)})
            for a, b in intervals]
