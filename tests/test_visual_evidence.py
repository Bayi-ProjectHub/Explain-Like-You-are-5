"""Test motion summaries without relying on detector scores or model downloads."""

from types import SimpleNamespace

import numpy as np

from src.delivery.video import FrameSignals, detect_visual_events, summarize_window
from src.delivery.wholebody import WholeBodyTracker


def test_window_reports_all_four_visual_dimensions():
    before = FrameSignals(0.0, face_turn=0.1, iris_offset=0.0, torso_lean=4,
                          shoulders=(0.4, 0.5), shoulder_width=0.2, wrists={"left": (0.1, 0.0)},
                          face_coefficients={"jawOpen": 0.1})
    after = FrameSignals(0.2, face_turn=0.2, iris_offset=0.1, torso_lean=6,
                         shoulders=(0.44, 0.5), shoulder_width=0.2, wrists={"left": (0.4, 0.0)},
                         face_coefficients={"jawOpen": 0.3})
    assert summarize_window([before, after]) == {
        "face_turn_offset": 0.15, "iris_change_per_second": 0.5,
        "torso_lean_degrees": 5, "shoulder_motion_widths_per_second": 1,
        "gesture_bursts": 1, "wrist_range_shoulder_widths": 0.3,
        "wrist_speed_shoulder_widths_per_second": 1.5, "face_coefficient_change_per_second": 1,
    }


def test_missing_hands_and_gaps_do_not_create_gesture_counts():
    frames = [FrameSignals(0, wrists={"left": (0.0, 0.0)}), FrameSignals(0.2),
              FrameSignals(0.4, wrists={"left": (0.5, 0.0)}),
              FrameSignals(1.4, wrists={"left": (1.0, 0.0)})]
    assert summarize_window(frames) == {}


def test_visual_events_follow_frame_timestamps_across_window_boundary():
    frames = [FrameSignals(t, wrists={"left": (x, 0.0)}) for t, x in
              [(1.9, 0), (2.0, 0.2), (2.1, 0.4), (2.2, 0.4), (2.3, 0.6), (2.4, 0.8)]]
    events = detect_visual_events(frames)
    assert [(event.start, event.end) for event in events] == [(1.9, 2.1), (2.2, 2.4)]


def test_wrist_lift_and_lowering_have_signed_measurements_and_stop_at_a_cut():
    frames = [FrameSignals(time, wrists={"right": (0.2, y)}, scene_cut=cut) for time, y, cut in
              [(0.0, 0.5, False), (0.1, 0.3, False), (0.2, 0.1, False), (0.3, 0.35, False),
               (0.4, 0.5, False), (0.5, 0.8, True)]]
    lift, lower = detect_visual_events(frames)
    assert (lift.start, lift.end, lower.start, lower.end) == (0.0, 0.2, 0.2, 0.4)
    first = lift.measurements[0]
    assert (first.target, first.axis, first.unit, first.delta) == ("right_wrist", "y", "shoulder_width", -0.4)
    assert (lower.measurements[0].start_value, lower.measurements[0].end_value) == (0.1, 0.5)


def test_single_frame_wrist_jump_is_not_a_gesture():
    before = FrameSignals(111.695, wrists={"left": (0.0, 0.3634)})
    after = FrameSignals(111.737, wrists={"left": (0.0, 0.2081)})
    assert detect_visual_events([before, after]) == []


def test_face_coefficients_are_named_and_model_switch_is_not_an_action():
    frames = [
        FrameSignals(0.0, face_coefficients={"eyeBlinkLeft": 0.05}),
        FrameSignals(0.1, face_coefficients={"eyeBlinkLeft": 0.6}),
        FrameSignals(0.2, face_coefficients={"eyeBlinkLeft": 0.07}, face_source="face_specialized"),
    ]
    event, = detect_visual_events(frames)
    measurement, = event.measurements
    assert (event.kind, event.start, event.end) == ("face", 0.0, 0.1)
    assert (measurement.target, measurement.unit, measurement.direction) == ("eyeBlinkLeft", "blendshape_coefficient", "increase")


def test_wholebody_does_not_count_extrapolated_hands_in_a_closeup():
    tracker = WholeBodyTracker.__new__(WholeBodyTracker)
    points = np.full((1, 133, 2), 50)
    tracker.detector = lambda image: (points, np.ones((1, 133)))
    result = SimpleNamespace(pose_landmarks=[], left_hand_landmarks=[], right_hand_landmarks=[])
    assert tracker.fill(np.zeros((100, 100, 3), dtype=np.uint8), result)
    assert result.pose_landmarks[11].visibility == 1
    assert [result.pose_landmarks[i].visibility for i in (15, 16)] == [0, 0]
    assert not result.left_hand_landmarks and not result.right_hand_landmarks
