"""TrackBench evaluation package (CLEAR MOT metrics + mining stubs)."""

__version__ = "0.1.0"

from eval.metrics import FrameMatch, MotMetrics, evaluate_scene, load_jsonl

__all__ = [
    "FrameMatch",
    "MotMetrics",
    "evaluate_scene",
    "load_jsonl",
]
