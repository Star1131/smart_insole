from __future__ import annotations

import math

from utils.math_utils import normalize_quaternion, quaternion_to_euler


def test_normalize_quaternion_returns_identity_for_zero_norm() -> None:
    assert normalize_quaternion(0.0, 0.0, 0.0, 0.0) == (1.0, 0.0, 0.0, 0.0)


def test_normalize_quaternion_normalizes_non_unit_quaternion() -> None:
    w, x, y, z = normalize_quaternion(2.0, 0.0, 0.0, 0.0)
    assert math.isclose(w, 1.0, rel_tol=1e-9, abs_tol=1e-9)
    assert math.isclose(x, 0.0, rel_tol=1e-9, abs_tol=1e-9)
    assert math.isclose(y, 0.0, rel_tol=1e-9, abs_tol=1e-9)
    assert math.isclose(z, 0.0, rel_tol=1e-9, abs_tol=1e-9)


def test_quaternion_to_euler_90_degree_yaw() -> None:
    yaw_90 = math.sqrt(0.5)
    roll, pitch, yaw = quaternion_to_euler(yaw_90, 0.0, 0.0, yaw_90)

    assert math.isclose(roll, 0.0, abs_tol=1e-6)
    assert math.isclose(pitch, 0.0, abs_tol=1e-6)
    assert math.isclose(yaw, 90.0, abs_tol=1e-6)
