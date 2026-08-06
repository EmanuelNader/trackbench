"""Tracking metrics (stubs — implemented in M2)."""

from __future__ import annotations

from typing import Any, Sequence


def mota(*_args: Any, **_kwargs: Any) -> float:
    """Multiple Object Tracking Accuracy (MOTA).

    Not implemented until M2.
    """
    raise NotImplementedError("MOTA is not implemented until M2")


def motp(*_args: Any, **_kwargs: Any) -> float:
    """Multiple Object Tracking Precision (MOTP).

    Not implemented until M2.
    """
    raise NotImplementedError("MOTP is not implemented until M2")


def idsw(*_args: Any, **_kwargs: Any) -> int:
    """Identity switch count.

    Not implemented until M2.
    """
    raise NotImplementedError("IDSW is not implemented until M2")


def fragmentations(*_args: Any, **_kwargs: Any) -> int:
    """Track fragmentation count.

    Not implemented until M2.
    """
    raise NotImplementedError("fragmentations is not implemented until M2")


def summarize_metrics(
    gt_frames: Sequence[Any],
    pred_frames: Sequence[Any],
    **_kwargs: Any,
) -> dict[str, float]:
    """Return a placeholder metrics dict; real computation lands in M2."""
    _ = (gt_frames, pred_frames)
    return {
        "mota": float("nan"),
        "motp": float("nan"),
        "idsw": float("nan"),
        "frag": float("nan"),
    }
