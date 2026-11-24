"""Optional RTMW WholeBody for CPU, CUDA or Windows DirectML."""

import os
from math import hypot
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from .landmarks import pose_quality, visible

BODY_MAP = {11: 5, 12: 6, 15: 9, 16: 10, 23: 11, 24: 12}


class WholeBodyTracker:
    def __init__(self, directory: Path, device: str, preset: str):
        import onnxruntime as ort
        from rtmlib import Wholebody

        providers = {"cpu": "CPUExecutionProvider", "cuda": "CUDAExecutionProvider", "dml": "DmlExecutionProvider"}
        if device not in providers or preset not in {"m", "l"}:
            raise ValueError("RTMW device must be cpu/cuda/dml and preset must be m/l.")
        provider = providers[device]
        if provider not in ort.get_available_providers():
            raise RuntimeError(f"{provider} is unavailable. Configure the matching ONNX runtime or use CPU.")
        detector = directory / "yolox-tiny.onnx"
        model = directory / f"pose-{preset}.onnx"
        if not detector.is_file() or not model.is_file():
            raise FileNotFoundError(f"Expected local RTMW weights: {detector.name}, {model.name}")
        self.detector = Wholebody(det=str(detector), det_input_size=(416, 416), pose=str(model),
                                  pose_input_size=(192, 256) if preset == "m" else (288, 384),
                                  backend="onnxruntime", device="cpu" if device == "dml" else device,
                                  to_openpose=False)
        self.source = f"rtmw_{preset}_{device}"
        sessions = (self.detector.det_model, self.detector.pose_model)
        if device == "dml":
            # DirectML needs sequential execution with memory-pattern optimization disabled.
            options = ort.SessionOptions()
            options.enable_mem_pattern = False
            options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            adapter = int(os.environ.get("VIDEO_RTMW_DML_DEVICE_ID", "0"))
            for tool in sessions:
                tool.session = ort.InferenceSession(tool.onnx_model, sess_options=options,
                                                   providers=[(provider, {"device_id": str(adapter)}),
                                                              "CPUExecutionProvider"])
        if any(provider not in tool.session.get_providers() for tool in sessions):
            raise RuntimeError(f"RTMW failed to initialize {provider}.")

    @classmethod
    def configured(cls):
        directory = os.environ.get("VIDEO_RTMW_DIR")
        if not directory:
            return None
        return cls(Path(directory), os.environ.get("VIDEO_RTMW_DEVICE", "cpu"), os.environ.get("VIDEO_RTMW_PRESET", "m"))

    def fill(self, rgb: np.ndarray, result) -> bool:
        points, scores = self.detector(np.ascontiguousarray(rgb[:, :, ::-1]))  # RTMLib takes BGR.
        if len(points) != 1 or len(points[0]) != 133:
            # This adapter deliberately handles a single visible presenter. Multi-person
            # selection needs an identity tracker shared by the face and pose detectors.
            return False
        height, width = rgb.shape[:2]

        def point(index):
            x, y = points[0][index]
            score = float(scores[0][index])
            return SimpleNamespace(x=float(x / width), y=float(y / height), visibility=score)

        pose = [SimpleNamespace(x=0.0, y=0.0, visibility=0.0) for _ in range(33)]
        for target, source in BODY_MAP.items():
            pose[target] = point(source)
        original = result.pose_landmarks
        for index, hand in ((15, result.left_hand_landmarks), (16, result.right_hand_landmarks)):
            # A WholeBody model can confidently extrapolate wrists/fingers in a face close-up.
            # Require independent wrist evidence before using its trajectory.
            observed = hand[0] if hand else original[index] if len(original) == 33 and visible(original[index]) else None
            if observed is None or hypot(observed.x - pose[index].x, observed.y - pose[index].y) > 0.13:
                pose[index].visibility = 0.0
        quality = pose_quality(pose)
        if quality == 0 or quality < pose_quality(result.pose_landmarks):
            return False
        result.pose_landmarks = pose
        return True
