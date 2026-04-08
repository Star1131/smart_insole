from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Tuple

import numpy as np

Quaternion = Tuple[float, float, float, float]
EulerAngles = Tuple[float, float, float]
CopPosition = Optional[Tuple[float, float]]
Matrix8x16 = np.ndarray


@dataclass
class RawPacket:
    """协议层解析出的单个子包。"""

    seq: int
    sensor_type: int
    payload: bytes
    recv_ts: float


@dataclass
class MergedFrame:
    """按 sensor_type 合并后的完整 272 字节帧。"""

    sensor_type: int
    data: bytes
    timestamp: float


@dataclass
class SensorFrame:
    """解码后的结构化传感器数据。"""

    timestamp: float
    sensor_type: int
    adc_data: Matrix8x16
    imu_quaternion: Quaternion


@dataclass
class FootZone:
    """足底分区定义。"""

    name: str
    display_name: str
    row_start: int
    row_end: int
    valid_mask: Optional[np.ndarray] = None


@dataclass
class ZoneMetrics:
    """单分区实时指标。"""

    zone_name: str
    avg_adc: float
    valid_count: int
    total_adc: int
    pressure_kpa: Optional[float] = None


@dataclass
class ProcessedFrame:
    """业务处理后的完整帧（供 UI 和录制模块消费）。"""

    timestamp: float
    sensor_type: int
    adc_raw: Matrix8x16
    adc_filtered: Matrix8x16
    adc_calibrated: Matrix8x16
    imu_quaternion: Quaternion
    imu_euler: EulerAngles
    total_pressure: float
    cop: CopPosition
    peak_pressure: float
    peak_position: tuple[int, int]
    fps: float
    frame_index: int
    zone_metrics: dict[str, ZoneMetrics] = field(default_factory=dict)


@dataclass
class CalibrationPoint:
    """单个分区标定采样点。"""

    pressure_kpa: float
    avg_adc: float
    adc_std: float
    sample_count: int
    position_label: str = ""
    repeat_index: int = 1


@dataclass
class ZoneCalibrationResult:
    """单分区标定结果。"""

    zone_name: str
    zero_offset: float
    a: float
    b: float
    r_squared: float
    valid_sensor_count: int
    data_points: list[CalibrationPoint] = field(default_factory=list)


@dataclass
class CalibrationProfile:
    """标定参数档案（兼容旧版 + 分区标定 v2）。"""

    # v2 核心字段
    version: str = "2.0"
    device_id: str = ""
    contact_area_cm2: float = 0.0
    noise_threshold: int = 10
    zone_config: dict[str, dict[str, Any]] = field(default_factory=dict)
    zones: dict[str, ZoneCalibrationResult] = field(default_factory=dict)
    created_at: str = ""

    # 兼容旧版字段（全局标定）
    fit_method: str = "linear"
    zero_offset: float = 0.0
    coefficients: dict[str, float] = field(default_factory=dict)
    r_squared: float = 0.0
    data_points: list[dict[str, Any]] = field(default_factory=list)
