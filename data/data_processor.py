from __future__ import annotations

import struct
from collections import deque
from time import monotonic

import numpy as np
from PySide6.QtCore import QObject, Signal

from config import (
    ADC_COLS,
    ADC_FLIP_LEFT_RIGHT,
    ADC_FLIP_UP_DOWN,
    ADC_NOISE_THRESHOLD,
    ADC_ROWS,
    ADC_USE_HIGH_HALF,
    DEFAULT_FOOT_ZONES,
)
from data.models import (
    CalibrationProfile,
    FootZone,
    MergedFrame,
    ProcessedFrame,
    ZoneCalibrationResult,
    ZoneMetrics,
)


class DataProcessor(QObject):
    frame_processed = Signal(object)

    def __init__(self, fps_window_size: int = 60) -> None:
        super().__init__()
        self._frame_index = 0
        self._display_mode = "raw"
        self._calibration_profile: CalibrationProfile | None = None
        self._frame_ts_window: deque[float] = deque(maxlen=max(2, fps_window_size))
        self._rows, self._cols = np.indices((ADC_ROWS, ADC_COLS), dtype=np.float64)
        self._noise_threshold = int(ADC_NOISE_THRESHOLD)
        self._zones: list[FootZone] = self._load_default_zones()
        self._valid_mask: np.ndarray | None = None

    def on_merged_frame(self, frame: MergedFrame) -> None:
        if len(frame.data) < 272:
            return

        adc_raw = self._decode_adc_matrix(frame.data)
        adc_filtered = adc_raw.copy()
        adc_filtered[adc_filtered < self._noise_threshold] = 0
        imu_quaternion = self._decode_quaternion(frame.data[256:272])
        imu_euler = self._quaternion_to_euler(*imu_quaternion)

        zone_metrics = self._compute_zone_metrics(adc_filtered)
        adc_calibrated = self._apply_calibration(adc_filtered.astype(np.float64), zone_metrics)
        metrics_matrix = adc_filtered.astype(np.float64) if self._display_mode == "raw" else adc_calibrated

        total_pressure = float(np.sum(metrics_matrix[metrics_matrix > 0.0]))
        cop = self._compute_cop(metrics_matrix, total_pressure)
        peak_index = int(np.argmax(metrics_matrix))
        peak_position = tuple(int(v) for v in np.unravel_index(peak_index, (ADC_ROWS, ADC_COLS)))
        peak_pressure = float(metrics_matrix[peak_position])
        fps = self._update_fps(frame.timestamp)

        self._frame_index += 1
        self.frame_processed.emit(
            ProcessedFrame(
                timestamp=frame.timestamp,
                sensor_type=frame.sensor_type,
                adc_raw=adc_raw,
                adc_filtered=adc_filtered,
                adc_calibrated=adc_calibrated,
                imu_quaternion=imu_quaternion,
                imu_euler=imu_euler,
                total_pressure=total_pressure,
                cop=cop,
                peak_pressure=peak_pressure,
                peak_position=peak_position,
                zone_metrics=zone_metrics,
                fps=fps,
                frame_index=self._frame_index,
            )
        )

    def set_calibration(self, profile: CalibrationProfile) -> None:
        self._calibration_profile = profile

    def clear_calibration(self) -> None:
        self._calibration_profile = None

    def set_display_mode(self, mode: str) -> None:
        if mode in ("raw", "calibrated"):
            self._display_mode = mode

    def set_zones(self, zones: list[FootZone]) -> None:
        self._zones = [z for z in zones if 0 <= z.row_start <= z.row_end <= ADC_ROWS - 1] or self._load_default_zones()

    def detect_valid_mask(self, frames: list[np.ndarray]) -> np.ndarray:
        if not frames:
            self._valid_mask = np.ones((ADC_ROWS, ADC_COLS), dtype=bool)
            return self._valid_mask
        stack = np.asarray(frames, dtype=np.float64)
        if stack.ndim != 3 or stack.shape[1:] != (ADC_ROWS, ADC_COLS):
            self._valid_mask = np.ones((ADC_ROWS, ADC_COLS), dtype=bool)
            return self._valid_mask
        self._valid_mask = np.any(stack > 0.0, axis=0)
        return self._valid_mask

    def _decode_quaternion(self, payload: bytes) -> tuple[float, float, float, float]:
        if len(payload) != 16:
            return 1.0, 0.0, 0.0, 0.0
        try:
            w, x, y, z = struct.unpack("<4f", payload)
        except struct.error:
            return 1.0, 0.0, 0.0, 0.0
        return self._normalize_quaternion(w, x, y, z)

    def _normalize_quaternion(self, w: float, x: float, y: float, z: float) -> tuple[float, float, float, float]:
        norm = float(np.sqrt(w * w + x * x + y * y + z * z))
        if norm <= 1e-8:
            return 1.0, 0.0, 0.0, 0.0
        return w / norm, x / norm, y / norm, z / norm

    def _decode_adc_matrix(self, merged_data: bytes) -> np.ndarray:
        block_size = ADC_ROWS * ADC_COLS
        adc_payload = np.frombuffer(merged_data[:256], dtype=np.uint8)
        if adc_payload.size < block_size:
            return np.zeros((ADC_ROWS, ADC_COLS), dtype=np.uint8)

        block = adc_payload[block_size:2 * block_size] if ADC_USE_HIGH_HALF else adc_payload[:block_size]
        matrix = block.reshape(ADC_COLS, ADC_ROWS).T.copy()
        if ADC_FLIP_LEFT_RIGHT:
            matrix = np.fliplr(matrix)
        if ADC_FLIP_UP_DOWN:
            matrix = np.flipud(matrix)
        return matrix

    def _quaternion_to_euler(self, w: float, x: float, y: float, z: float) -> tuple[float, float, float]:
        sinr_cosp = 2.0 * (w * x + y * z)
        cosr_cosp = 1.0 - 2.0 * (x * x + y * y)
        roll = float(np.degrees(np.arctan2(sinr_cosp, cosr_cosp)))

        sinp = 2.0 * (w * y - z * x)
        sinp = float(np.clip(sinp, -1.0, 1.0))
        pitch = float(np.degrees(np.arcsin(sinp)))

        siny_cosp = 2.0 * (w * z + x * y)
        cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
        yaw = float(np.degrees(np.arctan2(siny_cosp, cosy_cosp)))
        return roll, pitch, yaw

    def _apply_calibration(self, adc_data: np.ndarray, zone_metrics: dict[str, ZoneMetrics]) -> np.ndarray:
        profile = self._calibration_profile
        if profile is None:
            return adc_data

        zone_matrix = self._apply_zone_calibration(adc_data, profile, zone_metrics)
        if zone_matrix is not None:
            return zone_matrix

        # 兼容旧版全局标定
        x = np.maximum(adc_data - float(profile.zero_offset), 0.0)
        method = profile.fit_method.lower()
        coeff = profile.coefficients

        if method == "linear":
            a = float(coeff.get("a", 1.0))
            b = float(coeff.get("b", 0.0))
            return a * x + b
        if method in ("poly2", "polynomial", "quadratic"):
            a = float(coeff.get("a", 0.0))
            b = float(coeff.get("b", 1.0))
            c = float(coeff.get("c", 0.0))
            return a * (x**2) + b * x + c
        if method == "piecewise":
            knot = float(coeff.get("knot", 0.0))
            a1 = float(coeff.get("a1", 1.0))
            b1 = float(coeff.get("b1", 0.0))
            a2 = float(coeff.get("a2", a1))
            b2 = float(coeff.get("b2", b1))
            return np.where(x <= knot, a1 * x + b1, a2 * x + b2)
        return x

    def _apply_zone_calibration(
        self,
        adc_data: np.ndarray,
        profile: CalibrationProfile,
        zone_metrics: dict[str, ZoneMetrics],
    ) -> np.ndarray | None:
        if not profile.zones:
            return None

        calibrated = np.zeros_like(adc_data, dtype=np.float64)
        for zone in self._zones:
            if zone.name not in profile.zones:
                continue
            metric = zone_metrics.get(zone.name)
            if metric is None:
                continue

            zone_result = profile.zones[zone.name]
            if isinstance(zone_result, ZoneCalibrationResult):
                zero_offset = float(zone_result.zero_offset)
                a = float(zone_result.a)
                b = float(zone_result.b)
            else:
                zero_offset = float(zone_result.get("zero_offset", 0.0))
                a = float(zone_result.get("a", 1.0))
                b = float(zone_result.get("b", 0.0))

            pressure_kpa = a * max(metric.avg_adc - zero_offset, 0.0) + b
            metric.pressure_kpa = float(pressure_kpa)

            region = adc_data[zone.row_start : zone.row_end + 1, :]
            if self._valid_mask is not None:
                mask_region = self._valid_mask[zone.row_start : zone.row_end + 1, :]
                region_source = np.where(mask_region, region, 0.0)
            else:
                region_source = region

            region_cal = self._scale_zone_region_preserving_shape(
                region_source=region_source,
                target_pressure_kpa=float(pressure_kpa),
            )
            calibrated[zone.row_start : zone.row_end + 1, :] = region_cal
        return calibrated

    @staticmethod
    def _scale_zone_region_preserving_shape(
        region_source: np.ndarray,
        target_pressure_kpa: float,
    ) -> np.ndarray:
        region = np.asarray(region_source, dtype=np.float64)
        region_cal = np.zeros_like(region, dtype=np.float64)

        active_mask = region > 0.0
        if not np.any(active_mask):
            return region_cal

        active_values = region[active_mask]
        mean_value = float(np.mean(active_values))
        if mean_value <= 1e-12:
            return region_cal

        scale = float(target_pressure_kpa) / mean_value
        region_cal[active_mask] = active_values * scale
        return region_cal

    def _compute_zone_metrics(self, adc_filtered: np.ndarray) -> dict[str, ZoneMetrics]:
        metrics: dict[str, ZoneMetrics] = {}
        for zone in self._zones:
            region = adc_filtered[zone.row_start : zone.row_end + 1, :]
            if self._valid_mask is not None:
                mask_region = self._valid_mask[zone.row_start : zone.row_end + 1, :]
                region = np.where(mask_region, region, 0)

            valid_pixels = region[region >= self._noise_threshold]
            valid_count = int(valid_pixels.size)
            total_adc = int(np.sum(valid_pixels))
            avg_adc = float(total_adc / valid_count) if valid_count > 0 else 0.0
            metrics[zone.name] = ZoneMetrics(
                zone_name=zone.name,
                avg_adc=avg_adc,
                valid_count=valid_count,
                total_adc=total_adc,
                pressure_kpa=None,
            )
        return metrics

    @staticmethod
    def _load_default_zones() -> list[FootZone]:
        zones: list[FootZone] = []
        for item in DEFAULT_FOOT_ZONES:
            zones.append(
                FootZone(
                    name=str(item["name"]),
                    display_name=str(item["display_name"]),
                    row_start=int(item["row_start"]),
                    row_end=int(item["row_end"]),
                )
            )
        return zones

    def _compute_cop(self, matrix: np.ndarray, total_pressure: float) -> tuple[float, float] | None:
        if total_pressure <= 0.0:
            return None
        cop_r = float(np.sum(matrix * self._rows) / total_pressure)
        cop_c = float(np.sum(matrix * self._cols) / total_pressure)
        return cop_r, cop_c

    def _update_fps(self, timestamp: float) -> float:
        ts = float(timestamp)
        if self._frame_ts_window and ts <= self._frame_ts_window[-1]:
            ts = monotonic()
        self._frame_ts_window.append(ts)

        if len(self._frame_ts_window) < 2:
            return 0.0
        elapsed = self._frame_ts_window[-1] - self._frame_ts_window[0]
        if elapsed <= 0.0:
            return 0.0
        return float((len(self._frame_ts_window) - 1) / elapsed)
