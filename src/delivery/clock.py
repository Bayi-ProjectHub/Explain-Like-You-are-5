"""Read the original container clock without changing the main audio pipeline."""

from pathlib import Path

import av


def audio_playback_offset(path: Path) -> float:
    with av.open(str(path)) as media:
        origin = (media.start_time or 0) / av.time_base
        first = next(media.decode(audio=0), None)
        if first is None or first.time is None:
            return 0.0
        return round(first.time - origin, 6)
