"""Optional MediaPipe fallback detectors for missed landmarks on usable frames."""

from contextlib import ExitStack
from math import hypot
import os
from pathlib import Path


def visible(point) -> bool:
    return (point.visibility or 0) >= 0.5 and 0 <= point.x <= 1 and 0 <= point.y <= 1


def pose_quality(points) -> int:
    if len(points) < 33 or not (visible(points[11]) and visible(points[12])):
        return 0
    return sum(visible(points[i]) for i in (11, 12, 15, 16, 23, 24))


class LandmarkFallbacks:
    def __init__(self, mp, stack: ExitStack, directory: Path):
        vision = mp.tasks.vision
        pose_path = directory / "pose_landmarker_heavy.task"
        face_path = directory / "face_landmarker.task"
        hand_path = directory / "hand_landmarker.task"

        def base(path):
            return mp.tasks.BaseOptions(model_asset_path=str(path))

        self.pose = stack.enter_context(vision.PoseLandmarker.create_from_options(
            vision.PoseLandmarkerOptions(base_options=base(pose_path), running_mode=vision.RunningMode.IMAGE)
        )) if pose_path.is_file() else None
        self.face = stack.enter_context(vision.FaceLandmarker.create_from_options(
            vision.FaceLandmarkerOptions(base_options=base(face_path), output_face_blendshapes=True,
                                         running_mode=vision.RunningMode.VIDEO)
        )) if face_path.is_file() else None
        self.hand = stack.enter_context(vision.HandLandmarker.create_from_options(
            vision.HandLandmarkerOptions(base_options=base(hand_path), num_hands=2)
        )) if hand_path.is_file() else None
        self.face_mode = os.environ.get("VIDEO_FACE_MODE", "adaptive")
        if self.face_mode not in {"adaptive", "dedicated"}:
            raise ValueError("VIDEO_FACE_MODE must be adaptive or dedicated.")

    def fill(self, image, result, timestamp_ms: int) -> set[str]:
        used = set()
        primary_quality = pose_quality(result.pose_landmarks)
        # A close-up with reliable shoulders and a face may intentionally crop out hips and hands.
        if self.pose and (primary_quality == 0 or (primary_quality < 4 and not result.face_landmarks)):
            fallback = self.pose.detect(image)
            if fallback.pose_landmarks and pose_quality(fallback.pose_landmarks[0]) > primary_quality:
                result.pose_landmarks = fallback.pose_landmarks[0]
                used.add("pose_heavy")
        has_face = len(result.face_landmarks) >= 478 and bool(result.face_blendshapes)
        if self.face and (self.face_mode == "dedicated" or not has_face):
            fallback = self.face.detect_for_video(image, timestamp_ms)
            if fallback.face_landmarks:
                result.face_landmarks = fallback.face_landmarks[0]
                result.face_blendshapes = fallback.face_blendshapes[0] if fallback.face_blendshapes else []
                used.add("face_specialized")
        if self.hand and (not result.left_hand_landmarks or not result.right_hand_landmarks):
            pose = result.pose_landmarks
            if len(pose) >= 33 and (visible(pose[15]) or visible(pose[16])):
                candidates = list(self.hand.detect(image).hand_landmarks)
                for side, index in (("left", 15), ("right", 16)):
                    key = f"{side}_hand_landmarks"
                    if getattr(result, key) or not visible(pose[index]) or not candidates:
                        continue
                    wrist = pose[index]
                    distances = [hypot(hand[0].x - wrist.x, hand[0].y - wrist.y) for hand in candidates]
                    best = min(range(len(distances)), key=distances.__getitem__)
                    if distances[best] <= 0.10:
                        setattr(result, key, candidates.pop(best))
                        used.add("hand")
        return used
