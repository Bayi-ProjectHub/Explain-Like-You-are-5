"""Run Holistic on decoded frames, then aggregate observable signals by time."""

from dataclasses import dataclass, field
from math import atan2, degrees, dist, hypot
from pathlib import Path
from statistics import mean

import av
import numpy as np

from .schemas import Evidence, VisualEvent, VisualEvidence, VisualKind

SAMPLE_HZ = 10.0
WINDOW_SECONDS = 2.0
GESTURE_SPEED_THRESHOLD = 0.6  # Shoulder widths per second; an initial heuristic.
# Only report changes in movement-related coefficients. They are not emotions.
FACE_COEFFICIENTS = {"browInnerUp", "eyeBlinkLeft", "eyeBlinkRight", "jawOpen",
                     "mouthSmileLeft", "mouthSmileRight"}


@dataclass
class FrameSignals:
    time: float
    face_turn: float | None = None
    iris_offset: float | None = None
    torso_lean: float | None = None
    shoulders: tuple[float, float] | None = None
    shoulder_width: float | None = None
    wrists: dict[str, tuple[float, float]] = field(default_factory=dict)
    face_coefficients: dict[str, float] = field(default_factory=dict)


def frame_signals(result, time: float, aspect: float) -> FrameSignals:
    signals = FrameSignals(time)

    def xy(point):
        return (point.x * aspect, point.y)

    def midpoint(a, b):
        return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)

    def projected_position(point, start, end):
        dx, dy = end[0] - start[0], end[1] - start[1]
        length_squared = dx * dx + dy * dy
        if length_squared < 0.0001:
            return None
        return ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_squared

    face = result.face_landmarks
    if len(face) >= 478:
        turn = projected_position(xy(face[1]), xy(face[234]), xy(face[454]))
        if turn is not None:
            signals.face_turn = turn - 0.5
            # The 2D iris proxy is only meaningful near frontal views with both eyes visible.
            if abs(signals.face_turn) <= 0.18:
                left = projected_position(xy(face[468]), xy(face[33]), xy(face[133]))
                right = projected_position(xy(face[473]), xy(face[362]), xy(face[263]))
                if left is not None and right is not None and 0 <= left <= 1 and 0 <= right <= 1:
                    signals.iris_offset = mean((left, right)) - 0.5
        signals.face_coefficients = {
            item.category_name: item.score for item in result.face_blendshapes or []
            if item.category_name in FACE_COEFFICIENTS
        }

    pose = result.pose_landmarks
    if len(pose) < 33:
        return signals

    def visible(index):
        point = pose[index]
        return (point.visibility or 0) >= 0.5 and 0 <= point.x <= 1 and 0 <= point.y <= 1

    if visible(11) and visible(12):
        left, right = xy(pose[11]), xy(pose[12])
        width = dist(left, right)
        if width >= 0.05:
            signals.shoulders = midpoint(left, right)
            signals.shoulder_width = width
            if visible(23) and visible(24):
                hip = midpoint(xy(pose[23]), xy(pose[24]))
                dx, dy = signals.shoulders[0] - hip[0], hip[1] - signals.shoulders[1]
                if dy > 0.02:
                    signals.torso_lean = degrees(atan2(dx, dy))
            for name, index, hand, shoulder in (
                ("left", 15, result.left_hand_landmarks, left),
                ("right", 16, result.right_hand_landmarks, right),
            ):
                if len(hand) == 21 and visible(index):
                    wrist = xy(pose[index])
                    signals.wrists[name] = ((wrist[0] - shoulder[0]) / width,
                                             (wrist[1] - shoulder[1]) / width)
    return signals


def summarize_window(frames: list[FrameSignals]) -> dict[str, float | int]:
    metrics: dict[str, float | int] = {}

    def add_mean(name, values):
        if values:
            metrics[name] = round(mean(values), 4)

    add_mean("face_turn_offset", [f.face_turn for f in frames if f.face_turn is not None])
    add_mean("torso_lean_degrees", [f.torso_lean for f in frames if f.torso_lean is not None])
    hand_speeds, iris_changes, body_steps, face_changes = [], [], [], []
    gesture_bursts = 0
    was_moving = False
    hand_steps = {"left": [], "right": []}
    for before, after in zip(frames, frames[1:]):
        dt = after.time - before.time
        if not 0 < dt <= 2.5 / SAMPLE_HZ:
            was_moving = False
            continue
        if before.iris_offset is not None and after.iris_offset is not None:
            iris_changes.append(abs(after.iris_offset - before.iris_offset) / dt)
        if before.shoulders and after.shoulders:
            dx = after.shoulders[0] - before.shoulders[0]
            dy = after.shoulders[1] - before.shoulders[1]
            width = mean((before.shoulder_width, after.shoulder_width))
            body_steps.append(hypot(dx, dy) / width / dt)
        common = before.face_coefficients.keys() & after.face_coefficients.keys()
        if common:
            face_changes.append(mean(abs(after.face_coefficients[k] - before.face_coefficients[k])
                                     for k in common) / dt)
        speeds = []
        for hand in before.wrists.keys() & after.wrists.keys():
            speeds.append(dist(before.wrists[hand], after.wrists[hand]) / dt)
            hand_steps[hand].extend((before.wrists[hand], after.wrists[hand]))
        if speeds:
            hand_speeds.append(max(speeds))
        moving = bool(speeds and max(speeds) >= GESTURE_SPEED_THRESHOLD)
        gesture_bursts += moving and not was_moving
        was_moving = moving
    spans = []
    for points in hand_steps.values():
        if len(points) >= 2:
            xs, ys = zip(*points)
            spans.append(hypot(max(xs) - min(xs), max(ys) - min(ys)))
    if hand_speeds:
        metrics["gesture_bursts"] = gesture_bursts
        metrics["wrist_range_shoulder_widths"] = round(max(spans), 4)
    add_mean("wrist_speed_shoulder_widths_per_second", hand_speeds)
    add_mean("iris_change_per_second", iris_changes)
    add_mean("shoulder_motion_widths_per_second", body_steps)
    add_mean("face_coefficient_change_per_second", face_changes)
    return metrics


def detect_visual_events(frames: list[FrameSignals]) -> list[VisualEvent]:
    """Use sampled playback times, retaining separate bouts within a sentence."""
    thresholds: dict[VisualKind, dict[str, float]] = {
        "gesture": {"wrist_speed_shoulder_widths_per_second": GESTURE_SPEED_THRESHOLD},
        "gaze": {"head_turn_change_per_second": 0.35, "iris_change_per_second": 0.65},
        "posture": {"lean_change_degrees_per_second": 12, "shoulder_motion_widths_per_second": 0.8},
        "face": {"face_coefficient_change_per_second": 0.45},
    }
    events: list[VisualEvent] = []
    previous: dict[VisualKind, VisualEvent] = {}
    for before, after in zip(frames, frames[1:]):
        dt = after.time - before.time
        if not 0 < dt <= 2.5 / SAMPLE_HZ:
            continue
        measured = summarize_window([before, after])
        if before.face_turn is not None and after.face_turn is not None:
            measured["head_turn_change_per_second"] = abs(after.face_turn - before.face_turn) / dt
        if before.torso_lean is not None and after.torso_lean is not None:
            measured["lean_change_degrees_per_second"] = abs(after.torso_lean - before.torso_lean) / dt
        for kind, limits in thresholds.items():
            peaks = {metric: round(measured[metric], 3) for metric, limit in limits.items()
                     if measured.get(metric, 0) >= limit}
            if not peaks:
                continue
            start, end = round(before.time, 3), round(after.time, 3)
            last = previous.get(kind)
            if last is not None and last.end == start:
                last.end = end
                for metric, peak in peaks.items():
                    last.metrics[metric] = max(peak, last.metrics.get(metric, 0))
            else:
                event = VisualEvent(id=f"E{len(events) + 1}", start=start, end=end, kind=kind, metrics=peaks)
                events.append(event)
                previous[kind] = event
    return events


def analyze_video(path: Path, model_path: Path, max_seconds: int) -> VisualEvidence:
    import mediapipe as mp

    options = mp.tasks.vision.HolisticLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(model_path)),
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
        output_face_blendshapes=True,
    )
    frames: list[FrameSignals] = []
    next_sample = 0.0
    last_decoded = 0.0
    with mp.tasks.vision.HolisticLandmarker.create_from_options(options) as model, av.open(str(path)) as media:
        origin = (media.start_time or 0) / av.time_base
        for frame in media.decode(video=0):
            if frame.time is None:
                continue
            time = max(0.0, frame.time - origin)
            last_decoded = max(last_decoded, time)
            if time >= max_seconds:
                break
            if time < next_sample:
                continue
            next_sample = (int(time * SAMPLE_HZ) + 1) / SAMPLE_HZ
            scale = min(1.0, 640 / max(frame.width, frame.height))
            rgb = frame.reformat(width=max(1, round(frame.width * scale)),
                                 height=max(1, round(frame.height * scale)), format="rgb24").to_ndarray()
            rotation = getattr(frame, "rotation", 0)
            if rotation and rotation % 90 == 0:
                rgb = np.ascontiguousarray(np.rot90(rgb, rotation // 90))
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = model.detect_for_video(image, round(time * 1000))
            frames.append(frame_signals(result, time, rgb.shape[1] / rgb.shape[0]))

    coverage = {
        "face": sum(f.face_turn is not None for f in frames),
        "iris": sum(f.iris_offset is not None for f in frames),
        "upper_body": sum(f.shoulders is not None for f in frames),
        "hands": sum(bool(f.wrists) for f in frames),
    }
    by_window: dict[int, list[FrameSignals]] = {}
    for frame in frames:
        by_window.setdefault(int(frame.time / WINDOW_SECONDS), []).append(frame)
    windows = []
    for index, samples in by_window.items():
        metrics = summarize_window(samples)
        start, end = round(samples[0].time, 3), round(min((index + 1) * WINDOW_SECONDS, last_decoded), 3)
        if metrics and start < end:
            windows.append(Evidence(id=f"V{index + 1}", start=start, end=end, metrics=metrics))
    return VisualEvidence(sample_hz=SAMPLE_HZ, coverage={key: round(value / max(1, len(frames)), 3)
                                                        for key, value in coverage.items()}, windows=windows,
                          events=detect_visual_events(frames))
