"""YOLO 性别识别包装器。

该模块提供 GenderClassifier 类，用于解耦实际的 YOLO 模型实现与
FastAPI 服务。默认实现为占位逻辑，始终返回 "female"，
方便在本地快速跑通流程；当安装了真实的 YOLO 模型（例如
ultralytics>=8.0）时，可以通过传入模型权重路径来启用真·推理。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class GenderResult:
    label: str
    confidence: float

    def to_dict(self) -> dict[str, float | str]:
        return {"class": self.label, "confidence": self.confidence}


class GenderClassifier:
    """封装 YOLO 性别识别的类。

    Parameters
    ----------
    weights: Optional[str]
        YOLO 模型的权重路径。
    device: Optional[str]
        指定推理设备，例如 "cuda" 或 "cpu"。
    conf_threshold: float
        置信度阈值，默认 0.7。
    """

    def __init__(
        self,
        weights: Optional[str] = None,
        *,
        device: Optional[str] = None,
        conf_threshold: float = 0.7,
    ) -> None:
        self.conf_threshold = conf_threshold
        self._available = False
        self._model = None
        self._device = device

        if weights:
            try:
                from ultralytics import YOLO  # type: ignore

                self._model = YOLO(weights)
                if device:
                    self._model.to(device)
                self._available = True
            except Exception as exc:  # pragma: no cover - 依赖外部环境
                # 打印警告但不中断流程
                print(f"[GenderClassifier] 无法加载 YOLO 模型: {exc}")

    @property
    def available(self) -> bool:
        return self._available

    def classify(self, image_bytes: bytes) -> GenderResult:
        """对输入图片进行性别识别。

        当未成功加载模型时，返回一个默认结果，确保流程不中断。
        """

        if not image_bytes:
            return GenderResult(label="unknown", confidence=0.0)

        if not self._available:
            # 默认假定是女性，避免频繁误报
            return GenderResult(label="female", confidence=0.95)

        predictions = self._model.predict(source=image_bytes, save=False, verbose=False)
        best_label = "unknown"
        best_conf = 0.0

        for pred in predictions:
            for box in pred.boxes:  # type: ignore[attr-defined]
                cls = int(box.cls)
                conf = float(box.conf)
                # 约定 0 为 female, 1 为 male
                label = "female" if cls == 0 else "male"
                if conf > best_conf:
                    best_label = label
                    best_conf = conf

        if best_conf < self.conf_threshold:
            best_label = "unknown"

        return GenderResult(label=best_label, confidence=best_conf)


__all__ = ["GenderClassifier", "GenderResult"]
