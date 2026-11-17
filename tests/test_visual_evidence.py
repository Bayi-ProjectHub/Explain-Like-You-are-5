"""Test motion summaries without relying on detector scores or model downloads."""

from src.delivery.video import FrameSignals, detect_visual_events, summarize_window


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
              [(1.9, 0), (2.0, 0.2), (2.1, 0.4), (2.2, 0.4), (2.3, 0.6)]]
    events = detect_visual_events(frames)
    assert [(event.start, event.end) for event in events] == [(1.9, 2.1), (2.2, 2.3)]
