from __future__ import annotations

import math

_QUATERNION_EPSILON = 1e-8
_IDENTITY_QUATERNION = (1.0, 0.0, 0.0, 0.0)


def normalize_quaternion(w: float, x: float, y: float, z: float) -> tuple[float, float, float, float]:
    norm = math.sqrt(w * w + x * x + y * y + z * z)
    if norm <= _QUATERNION_EPSILON:
        return _IDENTITY_QUATERNION
    return w / norm, x / norm, y / norm, z / norm


def quaternion_to_euler(w: float, x: float, y: float, z: float) -> tuple[float, float, float]:
    w, x, y, z = normalize_quaternion(w, x, y, z)

    sinr_cosp = 2.0 * (w * x + y * z)
    cosr_cosp = 1.0 - 2.0 * (x * x + y * y)
    roll = math.degrees(math.atan2(sinr_cosp, cosr_cosp))

    sinp = 2.0 * (w * y - z * x)
    sinp = max(-1.0, min(1.0, sinp))
    pitch = math.degrees(math.asin(sinp))

    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    yaw = math.degrees(math.atan2(siny_cosp, cosy_cosp))
    return roll, pitch, yaw
