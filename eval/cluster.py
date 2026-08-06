"""Rule-based failure clustering (M3).

Buckets failure events by signature predicates. DBSCAN is stubbed only —
use it later if residual (unbucketed mass) is large; it is not the default.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Callable, Mapping, Sequence

Predicate = Callable[[Mapping[str, Any]], bool]


def _feat(event: Mapping[str, Any]) -> Mapping[str, Any]:
    f = event.get("features") or {}
    return f if isinstance(f, Mapping) else {}


def _str_contains(value: Any, needle: str) -> bool:
    if value is None:
        return False
    return needle.lower() in str(value).lower()


def _pred_far_lowvis_ped(event: Mapping[str, Any]) -> bool:
    f = _feat(event)
    vis = f.get("visibility")
    return (
        f.get("range_bin") == "far"
        and vis is not None
        and int(vis) <= 1
        and str(f.get("cls", "")).lower() == "pedestrian"
    )


def _pred_night_rain(event: Mapping[str, Any]) -> bool:
    f = _feat(event)
    return _str_contains(f.get("time_of_day"), "night") and _str_contains(
        f.get("weather"), "rain"
    )


def _pred_dense_id_switch(event: Mapping[str, Any]) -> bool:
    f = _feat(event)
    return event.get("kind") == "ID_SWITCH" and int(f.get("neighbor_count_5m") or 0) >= 3


def _pred_late_init_far(event: Mapping[str, Any]) -> bool:
    f = _feat(event)
    return event.get("kind") == "LATE_INIT" and f.get("range_bin") == "far"


def _pred_ghost_any(event: Mapping[str, Any]) -> bool:
    return event.get("kind") == "GHOST_TRACK"


def _pred_pos_spike(event: Mapping[str, Any]) -> bool:
    return event.get("kind") == "POS_ERROR_SPIKE"


# Ordered: first matching named rule wins.
RULE_BUCKETS: list[tuple[str, str, Predicate]] = [
    (
        "far_lowvis_ped",
        "Far-range low-visibility pedestrians",
        _pred_far_lowvis_ped,
    ),
    (
        "night_rain",
        "Nighttime rain failures",
        _pred_night_rain,
    ),
    (
        "dense_id_switch",
        "Identity switches in dense traffic",
        _pred_dense_id_switch,
    ),
    (
        "late_init_far",
        "Late track initialization at far range",
        _pred_late_init_far,
    ),
    (
        "ghost_any",
        "Ghost tracks (unmatched confirmed/coasting)",
        _pred_ghost_any,
    ),
    (
        "pos_spike",
        "Position error spikes",
        _pred_pos_spike,
    ),
]

_KIND_LABELS: dict[str, str] = {
    "ID_SWITCH": "Identity switches (other)",
    "TRACK_DROP": "Track drops (other)",
    "TRACK_DEATH": "Track deaths (other)",
    "GHOST_TRACK": "Ghost tracks (other)",
    "LATE_INIT": "Late initializations (other)",
    "POS_ERROR_SPIKE": "Position error spikes (other)",
}


def _event_id(event: Mapping[str, Any], index: int) -> str:
    if "id" in event and event["id"] is not None:
        return str(event["id"])
    kind = event.get("kind", "?")
    frame = event.get("frame", "?")
    gt = event.get("gt_id")
    tid = event.get("track_id")
    return f"{index}:{kind}:f{frame}:gt{gt}:tr{tid}"


def _centroid_summary(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Centroid-ish summary of a cluster's feature distribution."""
    if not events:
        return {}
    ranges = [float(_feat(e).get("range_m") or 0.0) for e in events]
    severities = [float(e.get("severity") or 0.0) for e in events]
    neighbors = [int(_feat(e).get("neighbor_count_5m") or 0) for e in events]
    durations = [int(_feat(e).get("duration_frames") or 0) for e in events]
    cls_counts = Counter(str(_feat(e).get("cls") or "unknown") for e in events)
    bin_counts = Counter(str(_feat(e).get("range_bin") or "unknown") for e in events)
    kind_counts = Counter(str(e.get("kind") or "unknown") for e in events)
    n = len(events)
    return {
        "n": n,
        "mean_range_m": sum(ranges) / n,
        "mean_severity": sum(severities) / n,
        "mean_neighbor_count_5m": sum(neighbors) / n,
        "mean_duration_frames": sum(durations) / n,
        "cls_mode": cls_counts.most_common(1)[0][0],
        "range_bin_mode": bin_counts.most_common(1)[0][0],
        "kind_mode": kind_counts.most_common(1)[0][0],
        "kinds": dict(kind_counts),
    }


def cluster_failures(
    failures: Sequence[dict[str, Any]],
    **_kwargs: Any,
) -> list[dict[str, Any]]:
    """Group failure events into rule buckets; leftovers fall back per kind.

    Returns clusters sorted by size descending. Each cluster:
    ``{bucket, label, size, event_indices, event_ids, summary}``.
    """
    buckets: dict[str, list[int]] = defaultdict(list)
    labels: dict[str, str] = {key: lab for key, lab, _ in RULE_BUCKETS}

    for idx, event in enumerate(failures):
        placed = False
        for key, _label, pred in RULE_BUCKETS:
            if pred(event):
                buckets[key].append(idx)
                placed = True
                break
        if not placed:
            kind = str(event.get("kind") or "UNKNOWN")
            key = f"other_{kind.lower()}"
            buckets[key].append(idx)
            labels.setdefault(key, _KIND_LABELS.get(kind, f"Other {kind}"))

    clusters: list[dict[str, Any]] = []
    for key, indices in buckets.items():
        evs = [failures[i] for i in indices]
        clusters.append(
            {
                "bucket": key,
                "label": labels.get(key, key),
                "size": len(indices),
                "event_indices": list(indices),
                "event_ids": [_event_id(failures[i], i) for i in indices],
                "summary": _centroid_summary(evs),
            }
        )

    clusters.sort(key=lambda c: (-c["size"], c["bucket"]))
    return clusters


def cluster_failures_dbscan(
    failures: Sequence[dict[str, Any]],
    **_kwargs: Any,
) -> list[dict[str, Any]]:
    """DBSCAN clustering stub.

    Only if residual large; not default. Prefer ``cluster_failures`` rule buckets.
    """
    raise NotImplementedError(
        "DBSCAN clustering is stubbed — only if residual large; not default"
    )
