"""Ego-frame geometric helpers (pure, unit-testable).

Convention (nuScenes lidar / ego):
  - x forward, y left, z up
  - yaw is rotation about z (radians), zero when facing +x

``global_to_ego`` takes an object's global translation and yaw plus the ego
pose (global translation + rotation quaternion) and returns ego-frame
``(x, y, z, yaw)``.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
from pyquaternion import Quaternion


def quat_to_yaw(rotation: Quaternion | Sequence[float]) -> float:
    """Yaw (rad about z) from a quaternion ``[w, x, y, z]`` or Quaternion."""
    q = rotation if isinstance(rotation, Quaternion) else Quaternion(rotation)
    heading = q.rotate(np.array([1.0, 0.0, 0.0]))
    return float(np.arctan2(heading[1], heading[0]))


def yaw_to_quat(yaw: float) -> Quaternion:
    """Quaternion representing a pure yaw about z."""
    return Quaternion(axis=[0.0, 0.0, 1.0], radians=yaw)


def global_to_ego(
    xyz_global: Sequence[float],
    yaw_global: float,
    ego_translation: Sequence[float],
    ego_rotation: Quaternion | Sequence[float],
) -> tuple[float, float, float, float]:
    """Transform a global point + yaw into the ego frame.

    Parameters
    ----------
    xyz_global:
        Object center in the global / world frame ``(x, y, z)``.
    yaw_global:
        Object heading about global z (radians).
    ego_translation:
        Ego pose translation in the global frame.
    ego_rotation:
        Ego pose rotation as Quaternion or ``[w, x, y, z]`` (global ← ego).

    Returns
    -------
    x, y, z, yaw
        Object pose expressed in the ego frame at this timestamp.
    """
    q_ego = (
        ego_rotation
        if isinstance(ego_rotation, Quaternion)
        else Quaternion(ego_rotation)
    )
    p_global = np.asarray(xyz_global, dtype=float).reshape(3)
    t_ego = np.asarray(ego_translation, dtype=float).reshape(3)

    p_ego = q_ego.inverse.rotate(p_global - t_ego)

    heading_global = np.array(
        [np.cos(yaw_global), np.sin(yaw_global), 0.0], dtype=float
    )
    heading_ego = q_ego.inverse.rotate(heading_global)
    yaw_ego = float(np.arctan2(heading_ego[1], heading_ego[0]))

    return float(p_ego[0]), float(p_ego[1]), float(p_ego[2]), yaw_ego


def nuscenes_size_to_lwh(size_wlh: Sequence[float]) -> tuple[float, float, float]:
    """Map nuScenes ``size = [w, l, h]`` to TrackBench ``(l, w, h)``."""
    w, l, h = (float(size_wlh[0]), float(size_wlh[1]), float(size_wlh[2]))
    return l, w, h
