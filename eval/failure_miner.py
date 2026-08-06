"""Failure mining over tracking runs (stub — M2+)."""

from __future__ import annotations

from typing import Any, Sequence


def mine_failures(
    gt_frames: Sequence[Any],
    pred_frames: Sequence[Any],
    **_kwargs: Any,
) -> list[dict[str, Any]]:
    """Extract per-event failure records (IDSW, misses, fragments, …).

    Not implemented until M2.
    """
    raise NotImplementedError("failure mining is not implemented until M2")
