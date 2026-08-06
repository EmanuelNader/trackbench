"""Ego-frame transform unit tests."""

import math

from pyquaternion import Quaternion

from ingest.transforms import global_to_ego, nuscenes_size_to_lwh, quat_to_yaw, yaw_to_quat


def test_identity_pose_preserves_coords():
    ego_t = [0.0, 0.0, 0.0]
    ego_r = Quaternion(axis=[0, 0, 1], radians=0.0)
    x, y, z, yaw = global_to_ego([3.0, -2.0, 1.0], 0.4, ego_t, ego_r)
    assert math.isclose(x, 3.0, abs_tol=1e-9)
    assert math.isclose(y, -2.0, abs_tol=1e-9)
    assert math.isclose(z, 1.0, abs_tol=1e-9)
    assert math.isclose(yaw, 0.4, abs_tol=1e-9)


def test_ego_yaw_90deg_rotates_point():
    """Ego facing +y (90° yaw): global +x point appears at ego -y."""
    ego_t = [0.0, 0.0, 0.0]
    ego_r = Quaternion(axis=[0, 0, 1], radians=math.pi / 2)
    x, y, z, yaw = global_to_ego([1.0, 0.0, 0.0], 0.0, ego_t, ego_r)
    assert math.isclose(x, 0.0, abs_tol=1e-9)
    assert math.isclose(y, -1.0, abs_tol=1e-9)
    assert math.isclose(z, 0.0, abs_tol=1e-9)
    # Object facing global +x; in ego (+y) frame that heading is -90° / -π/2
    assert math.isclose(yaw, -math.pi / 2, abs_tol=1e-9)


def test_ego_translation_subtracted():
    ego_t = [10.0, 5.0, 0.0]
    ego_r = [1.0, 0.0, 0.0, 0.0]  # identity quat [w,x,y,z]
    x, y, z, _ = global_to_ego([12.0, 5.0, 0.5], 0.0, ego_t, ego_r)
    assert math.isclose(x, 2.0, abs_tol=1e-9)
    assert math.isclose(y, 0.0, abs_tol=1e-9)
    assert math.isclose(z, 0.5, abs_tol=1e-9)


def test_quat_to_yaw_and_back():
    for angle in (0.0, 0.3, -1.2, math.pi / 2):
        q = yaw_to_quat(angle)
        assert math.isclose(quat_to_yaw(q), angle, abs_tol=1e-9)


def test_nuscenes_size_to_lwh():
    l, w, h = nuscenes_size_to_lwh([1.8, 4.5, 1.6])
    assert (l, w, h) == (4.5, 1.8, 1.6)
