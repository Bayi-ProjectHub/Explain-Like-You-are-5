"""Run Holistic on decoded frames, then aggregate observable signals by time."""

from collections import Counter
from contextlib import ExitStack
from dataclasses import dataclass, field
from math import atan2, degrees, dist, hypot
from pathlib import Path
from statistics import mean

import av
import numpy as np

from .landmarks import LandmarkFallbacks, visible as landmark_visible
from .schemas import Evidence, MotionMeasurement, PlaybackRange, VisualEvent, VisualEvidence, VisualKind
from .wholebody import WholeBodyTracker

SAMPLE_HZ = 15.0
MAX_FRAME_GAP = 0.28
WINDOW_SECONDS = 2.0
GESTURE_SPEED_THRESHOLD = 0.6  # Shoulder widths per second; an initial heuristic.
MIN_GESTURE_SECONDS = 0.12       # Discard single-sample wrist jumps at the target rate.
# Only report changes in movement-related coefficients. They are not emotions.
FACE_COEFFICIENTS = {"browInnerUp", "eyeBlinkLeft", "eyeBlinkRight", "jawOpen",
                     "mouthSmileLeft", "mouthSmileRight"}


class VideoReadError(ValueError):
    """The file has no usable video frames."""


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
    hands: set[str] = field(default_factory=set)
    pose_source: str = "holistic"
    face_source: str = "holistic"
    wrist_sources: dict[str, str] = field(default_factory=dict)
    scene_cut: bool = False
    scene_index: int = 0


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
        return landmark_visible(pose[index])

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
                has_pose_wrist = visible(index)
                if has_pose_wrist or len(hand) == 21:
                    wrist = xy(pose[index]) if has_pose_wrist else xy(hand[0])
                    signals.wrists[name] = ((wrist[0] - shoulder[0]) / width,
                                             (wrist[1] - shoulder[1]) / width)
                    signals.wrist_sources[name] = "pose" if has_pose_wrist else "hand"
                    if len(hand) == 21:
                        signals.hands.add(name)
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
        if after.scene_cut or not 0 < dt <= MAX_FRAME_GAP:
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
        "gaze": {"head_turn_change_per_second": 0.35, "iris_change_per_second": 0.65},
    }
    events: list[VisualEvent] = []
    previous: dict[VisualKind, VisualEvent] = {}
    for before, after in zip(frames, frames[1:]):
        dt = after.time - before.time
        if after.scene_cut or before.face_source != after.face_source or not 0 < dt <= MAX_FRAME_GAP:
            continue
        measured = summarize_window([before, after])
        if before.face_turn is not None and after.face_turn is not None:
            measured["head_turn_change_per_second"] = abs(after.face_turn - before.face_turn) / dt
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
    events.extend(directional_events(frames))
    events.sort(key=lambda event: (event.start, event.end, event.kind))
    for index, event in enumerate(events, 1):
        event.id = f"E{index}"
    return events


def directional_events(frames: list[FrameSignals]) -> list[VisualEvent]:
    """Keep left/right wrists and axes separate; split on reversals and occlusions."""
    events: list[VisualEvent] = []
    active: dict[tuple[str, str], VisualEvent] = {}
    for before, after in zip(frames, frames[1:]):
        dt = after.time - before.time
        if after.scene_cut or not 0 < dt <= MAX_FRAME_GAP:
            continue
        pairs = []
        if before.pose_source == after.pose_source:
            for side in ("left", "right"):
                if (side in before.wrists and side in after.wrists
                        and before.wrist_sources.get(side) == after.wrist_sources.get(side)):
                    for axis, a, b in zip(("x", "y"), before.wrists[side], after.wrists[side]):
                        pairs.append(("gesture", f"{side}_wrist", axis, "shoulder_width", a, b, 0.55))
            if before.shoulders and after.shoulders and before.shoulder_width and after.shoulder_width:
                scale = mean((before.shoulder_width, after.shoulder_width))
                for axis, a, b in zip(("x", "y"), before.shoulders, after.shoulders):
                    pairs.append(("posture", "shoulder_center", axis, "shoulder_width", 0.0, (b - a) / scale, 0.8))
            if before.torso_lean is not None and after.torso_lean is not None:
                pairs.append(("posture", "torso_lean", "roll", "degree", before.torso_lean, after.torso_lean, 12))
        if before.face_source == after.face_source:
            for action in sorted(before.face_coefficients.keys() & after.face_coefficients.keys()):
                pairs.append(("face", action, "coefficient", "blendshape_coefficient",
                              before.face_coefficients[action], after.face_coefficients[action], 0.65))

        start, end = round(before.time, 3), round(after.time, 3)
        for kind, target, axis, unit, a, b, threshold in pairs:
            delta = b - a
            speed = abs(delta) / dt
            if speed < threshold:
                continue
            key = (target, axis)
            last = active.get(key)
            if last and last.end == start and last.measurements[0].delta * delta > 0:
                previous = last.measurements[0]
                # Shoulder center is a displacement from the start of this bout.
                end_value = previous.end_value + delta if target == "shoulder_center" else b
                previous.end_value = round(end_value, 4)
                previous.delta = round(end_value - previous.start_value, 4)
                previous.span = abs(previous.delta)
                previous.peak_speed = round(max(previous.peak_speed, speed), 3)
                last.end = end
                continue
            measurement = MotionMeasurement(target=target, axis=axis, unit=unit,
                                            start_value=round(a, 4), end_value=round(b, 4),
                                            delta=round(delta, 4), span=round(abs(delta), 4),
                                            peak_speed=round(speed, 3))
            event = VisualEvent(id="", kind=kind, start=start, end=end, metrics={}, measurements=[measurement])
            events.append(event)
            active[key] = event
    return [event for event in events if significant_motion(event)]


def significant_motion(event: VisualEvent) -> bool:
    if event.kind == "gesture" and round(event.end - event.start, 3) < MIN_GESTURE_SECONDS:
        return False
    minimum_span = {"degree": 2.0, "shoulder_width": 0.08, "blendshape_coefficient": 0.16}
    return all(m.span >= minimum_span[m.unit] for m in event.measurements)


def analyze_video(path: Path, model_path: Path, max_seconds: int,
                  presenter_ranges: list[PlaybackRange] | None = None) -> VisualEvidence:
    frames: list[FrameSignals] = []
    next_sample = 0.0
    last_decoded = 0.0
    video_clock_origin = None
    video_offset = 0.0
    fallback_counts: Counter[str] = Counter()
    last_preview = None
    ranges = presenter_ranges or []
    selected_index = 0
    previous_range_index = None
    scene_index = 0
    with ExitStack() as stack, av.open(str(path)) as media:
        if not media.streams.video:
            raise VideoReadError("文件中没有视频画面，请重新选择。")

        import mediapipe as mp

        options = mp.tasks.vision.HolisticLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(model_path)),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            output_face_blendshapes=True,
        )
        model = stack.enter_context(mp.tasks.vision.HolisticLandmarker.create_from_options(options))
        fallbacks = LandmarkFallbacks(mp, stack, model_path.parent)
        wholebody = WholeBodyTracker.configured()
        playback_origin = (media.start_time or 0) / av.time_base
        for frame in media.decode(video=0):
            if frame.time is None:
                continue
            if video_clock_origin is None:
                video_clock_origin = frame.time
                video_offset = frame.time - playback_origin
            time = max(0.0, frame.time - video_clock_origin)
            last_decoded = max(last_decoded, time)
            if time >= max_seconds:
                break
            playback_time = time + video_offset
            while selected_index < len(ranges) and playback_time >= ranges[selected_index].end:
                selected_index += 1
            if ranges and selected_index == len(ranges):
                break
            if ranges and playback_time < ranges[selected_index].start:
                continue
            if time < next_sample:
                continue
            next_sample = (int(time * SAMPLE_HZ) + 1) / SAMPLE_HZ
            scale = min(2.0, 960 / max(frame.width, frame.height))
            rgb = frame.reformat(width=max(1, round(frame.width * scale)),
                                 height=max(1, round(frame.height * scale)), format="rgb24").to_ndarray()
            rotation = getattr(frame, "rotation", 0)
            if rotation and rotation % 90 == 0:
                rgb = np.ascontiguousarray(np.rot90(rgb, rotation // 90))
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = model.detect_for_video(image, round(time * 1000))
            used = fallbacks.fill(image, result, round(time * 1000))
            if wholebody is not None and wholebody.fill(rgb, result):
                used.add(wholebody.source)
            fallback_counts.update(used)
            signals = frame_signals(result, time, rgb.shape[1] / rgb.shape[0])
            if "face_specialized" in used:
                signals.face_source = "face_specialized"
            if "pose_heavy" in used:
                signals.pose_source = "pose_heavy"
            if wholebody is not None and wholebody.source in used:
                signals.pose_source = wholebody.source
            preview = rgb[np.linspace(0, rgb.shape[0] - 1, 16, dtype=int)][:,
                          np.linspace(0, rgb.shape[1] - 1, 16, dtype=int)].astype(np.float32)
            signals.scene_cut = previous_range_index != selected_index or (
                last_preview is not None and float(np.mean(abs(preview - last_preview))) > 43.0)
            scene_index += int(signals.scene_cut)
            signals.scene_index = scene_index
            previous_range_index = selected_index
            last_preview = preview
            frames.append(signals)

    if video_clock_origin is None:
        raise VideoReadError("视频里没有可读取的画面时间，请重新导出后上传。")

    coverage = {
        "face": sum(f.face_turn is not None for f in frames),
        "face_actions": sum(bool(f.face_coefficients) for f in frames),
        "iris": sum(f.iris_offset is not None for f in frames),
        "upper_body": sum(f.shoulders is not None for f in frames),
        "wrists": sum(bool(f.wrists) for f in frames),
        "hands": sum(bool(f.hands) for f in frames),
        "torso_lean": sum(f.torso_lean is not None for f in frames),
        "left_wrist": sum("left" in f.wrists for f in frames),
        "right_wrist": sum("right" in f.wrists for f in frames),
    }
    by_window: dict[tuple[int, int], list[FrameSignals]] = {}
    for frame in frames:
        key = (int(frame.time / WINDOW_SECONDS), frame.scene_index)
        by_window.setdefault(key, []).append(frame)
    windows = []
    for (index, _), samples in by_window.items():
        metrics = summarize_window(samples)
        start = round(samples[0].time, 3)
        end = round(min((index + 1) * WINDOW_SECONDS, last_decoded, samples[-1].time), 3)
        if metrics and start < end:
            windows.append(Evidence(id=f"V{len(windows) + 1}", start=start, end=end, metrics=metrics))
    return VisualEvidence(sample_hz=SAMPLE_HZ, coverage={key: round(value / max(1, len(frames)), 3)
                                                        for key, value in coverage.items()}, windows=windows,
                          events=detect_visual_events(frames), sampled_frames=len(frames),
                          video_offset_seconds=round(video_offset, 6), tracking_sources=dict(fallback_counts),
                          selected_playback_ranges=ranges)
