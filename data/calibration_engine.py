from __future__ import annotations

import csv
import json
import logging
import time
from datetime import datetime

import numpy as np
from PySide6.QtCore import QObject, Signal

from config import ADC_COLS, ADC_NOISE_THRESHOLD, ADC_ROWS, DEFAULT_FOOT_ZONES
from data.models import (
    CalibrationPoint,
    CalibrationProfile,
    FootZone,
    ZoneCalibrationResult,
)

logger = logging.getLogger(__name__)


class CalibrationEngine(QObject):
    """分区标定引擎：有效掩码检测 → 零点校准 → 多点采集 → 每区线性拟合 → JSON 持久化。"""

    mask_detected = Signal(object)
    collection_progress = Signal(float)
    collection_complete = Signal(str, object)
    zero_complete = Signal(dict)
    fit_complete = Signal(dict)

    def __init__(
        self,
        zones: list[FootZone] | None = None,
        noise_threshold: int = ADC_NOISE_THRESHOLD,
    ) -> None:
        super().__init__()
        self._zones = zones or _load_default_zones()
        self._noise_threshold = noise_threshold
        self._contact_area_cm2: float = 0.0
        self._device_id: str = ""

        self._collecting: bool = False
        self._collect_buffer: list[np.ndarray] = []
        self._collect_buffer_ts: list[float] = []
        self._collect_target_frames: int = 0
        self._collect_mode: str = ""
        self._collect_force_n: float = 0.0
        self._collect_zone_name: str | None = None
        self._collect_position_label: str = ""
        self._collect_repeat_index: int = 1

        self._valid_mask: np.ndarray | None = None
        self._zone_zero_offsets: dict[str, float] = {}
        self._zone_data_points: dict[str, list[CalibrationPoint]] = {
            z.name: [] for z in self._zones
        }
        self._raw_records: list[dict[str, str | float | int]] = []

    # ------------------------------------------------------------------
    # Step 0: 有效传感器掩码自动检测
    # ------------------------------------------------------------------

    def detect_valid_mask(
        self, frames: list[np.ndarray], threshold: int = 0
    ) -> np.ndarray:
        """采集约 1 s 数据，始终为 0 的位置标记为无效（无传感器）。"""
        if not frames:
            self._valid_mask = np.ones((ADC_ROWS, ADC_COLS), dtype=bool)
            return self._valid_mask

        stack = np.asarray(frames, dtype=np.float64)
        if stack.ndim != 3 or stack.shape[1:] != (ADC_ROWS, ADC_COLS):
            self._valid_mask = np.ones((ADC_ROWS, ADC_COLS), dtype=bool)
            return self._valid_mask

        self._valid_mask = np.any(stack > threshold, axis=0)
        self.mask_detected.emit(self._valid_mask.copy())
        logger.info(
            "Valid mask detected: %d/%d sensors active",
            int(np.sum(self._valid_mask)),
            self._valid_mask.size,
        )
        return self._valid_mask

    def start_mask_detection(
        self, duration_sec: float = 1.0, fps: int = 200
    ) -> None:
        """开始采集帧用于掩码检测。"""
        self._begin_collection("mask", duration_sec, fps)

    # ------------------------------------------------------------------
    # Step 1: 配置
    # ------------------------------------------------------------------

    def set_contact_area(self, area_cm2: float) -> None:
        if area_cm2 <= 0:
            raise ValueError("Contact area must be positive")
        self._contact_area_cm2 = area_cm2

    def set_device_id(self, device_id: str) -> None:
        self._device_id = device_id

    def set_zones(self, zones: list[FootZone]) -> None:
        self._zones = zones
        self._zone_data_points = {z.name: [] for z in self._zones}
        self._zone_zero_offsets = {}

    # ------------------------------------------------------------------
    # Step 2: 零点校准
    # ------------------------------------------------------------------

    def start_zero_calibration(
        self, duration_sec: float = 3.0, fps: int = 200
    ) -> None:
        """空载采集，完成后计算每区 zero_offset。"""
        self._begin_collection("zero", duration_sec, fps)

    # ------------------------------------------------------------------
    # Step 3: 多点压强采集
    # ------------------------------------------------------------------

    def start_point_collection(
        self,
        weight_kg: float | None = None,
        duration_sec: float = 3.0,
        fps: int = 200,
        zone_name: str | None = None,
        position_label: str = "",
        repeat_index: int = 1,
        force_n: float | None = None,
    ) -> None:
        """采集标定点，记录 (P_kPa, avg_ADC − offset) 数据对。

        兼容旧参数 `weight_kg`。若同时提供 `force_n` 与 `weight_kg`，优先使用 `force_n`。
        """
        if force_n is not None:
            self._collect_force_n = float(force_n)
        elif weight_kg is not None:
            self._collect_force_n = float(weight_kg) * 9.8
        else:
            raise ValueError("Either force_n or weight_kg must be provided")
        self._collect_zone_name = zone_name
        self._collect_position_label = position_label.strip()
        self._collect_repeat_index = max(1, int(repeat_index))
        self._begin_collection("point", duration_sec, fps)

    def feed_frame(self, adc_data: np.ndarray) -> None:
        """采集期间由外部调用，缓存帧数据。"""
        if not self._collecting:
            return
        if adc_data.shape != (ADC_ROWS, ADC_COLS):
            return

        self._collect_buffer.append(adc_data.copy())
        self._collect_buffer_ts.append(time.time())
        progress = len(self._collect_buffer) / self._collect_target_frames
        self.collection_progress.emit(min(progress, 1.0))

        if len(self._collect_buffer) >= self._collect_target_frames:
            self._collecting = False
            self._finish_collection()

    # ------------------------------------------------------------------
    # Step 4: 曲线拟合
    # ------------------------------------------------------------------

    def fit_all_zones(self) -> dict[str, ZoneCalibrationResult]:
        """对所有分区执行独立线性拟合。"""
        results: dict[str, ZoneCalibrationResult] = {}
        for zone in self._zones:
            result = self.fit_zone(zone.name)
            if result is not None:
                results[zone.name] = result
        self.fit_complete.emit(results)
        return results

    def fit_zone(self, zone_name: str) -> ZoneCalibrationResult | None:
        """单区线性拟合: P_kPa = a * (avg_ADC − offset) + b，计算 R²。"""
        points = self._zone_data_points.get(zone_name, [])
        if len(points) < 2:
            logger.warning("Zone '%s' has < 2 data points, cannot fit", zone_name)
            return None

        x = np.array([p.avg_adc for p in points])
        y = np.array([p.pressure_kpa for p in points])

        if np.ptp(x) == 0:
            logger.warning(
                "Zone '%s' ADC values are all identical (%.2f), cannot fit. "
                "Check if sensor data is reaching the calibration engine.",
                zone_name, float(x[0]),
            )
            return None

        try:
            coeffs = np.polyfit(x, y, deg=1)
        except np.linalg.LinAlgError:
            logger.error("Zone '%s' linear fit failed (SVD did not converge)", zone_name)
            return None
        a, b = float(coeffs[0]), float(coeffs[1])

        y_pred = a * x + b
        ss_res = float(np.sum((y - y_pred) ** 2))
        ss_tot = float(np.sum((y - np.mean(y)) ** 2))
        r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

        zone = next((z for z in self._zones if z.name == zone_name), None)
        valid_count = 0
        if zone is not None and self._valid_mask is not None:
            mask_region = self._valid_mask[zone.row_start : zone.row_end + 1, :]
            valid_count = int(np.sum(mask_region))

        result = ZoneCalibrationResult(
            zone_name=zone_name,
            zero_offset=self._zone_zero_offsets.get(zone_name, 0.0),
            a=a,
            b=b,
            r_squared=r_squared,
            valid_sensor_count=valid_count,
            data_points=list(points),
        )
        logger.info(
            "Zone '%s' fit: a=%.4f, b=%.4f, R²=%.4f", zone_name, a, b, r_squared
        )
        return result

    # ------------------------------------------------------------------
    # 参数管理 / JSON 导入导出
    # ------------------------------------------------------------------

    def build_profile(self) -> CalibrationProfile:
        """用当前标定数据构建完整 CalibrationProfile。"""
        results = self.fit_all_zones()
        zone_config: dict[str, dict] = {}
        for zone in self._zones:
            zone_config[zone.name] = {
                "row_start": zone.row_start,
                "row_end": zone.row_end,
                "display_name": zone.display_name,
            }
        return CalibrationProfile(
            version="2.0",
            device_id=self._device_id,
            contact_area_cm2=self._contact_area_cm2,
            noise_threshold=self._noise_threshold,
            zone_config=zone_config,
            zones=results,
            created_at=datetime.now().isoformat(timespec="seconds"),
        )

    def export_json(self, filepath: str) -> None:
        """将标定结果导出为 JSON v2.0 文件。"""
        profile = self.build_profile()
        data = _profile_to_dict(profile)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info("Calibration exported to %s", filepath)

    def export_raw_csv(self, filepath: str) -> None:
        """导出标定过程逐帧原始记录（每帧完整 ADC 矩阵 + 元数据）。"""
        fieldnames = [
            "timestamp",
            "zone_name",
            "position_label",
            "repeat_index",
            "frame_index",
            "contact_area_cm2",
            "pressure_kpa",
            "avg_adc",
            "adc_matrix_flat",
        ]
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self._raw_records)
        logger.info("Calibration raw records exported to %s (%d rows)", filepath, len(self._raw_records))

    @staticmethod
    def import_json(filepath: str) -> CalibrationProfile:
        """从 JSON 文件加载标定参数。"""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        profile = _dict_to_profile(data)
        logger.info(
            "Calibration imported from %s (v%s, %d zones)",
            filepath,
            profile.version,
            len(profile.zones),
        )
        return profile

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------

    @property
    def is_collecting(self) -> bool:
        return self._collecting

    @property
    def valid_mask(self) -> np.ndarray | None:
        return self._valid_mask

    @property
    def zone_zero_offsets(self) -> dict[str, float]:
        return dict(self._zone_zero_offsets)

    @property
    def zone_data_points(self) -> dict[str, list[CalibrationPoint]]:
        return dict(self._zone_data_points)

    def get_data_point_count(self, zone_name: str) -> int:
        return len(self._zone_data_points.get(zone_name, []))

    def reset(self) -> None:
        """重置全部标定数据。"""
        self._collecting = False
        self._collect_buffer = []
        self._collect_buffer_ts = []
        self._valid_mask = None
        self._zone_zero_offsets = {}
        self._zone_data_points = {z.name: [] for z in self._zones}
        self._raw_records = []

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _begin_collection(
        self, mode: str, duration_sec: float, fps: int
    ) -> None:
        self._collect_mode = mode
        self._collecting = True
        self._collect_buffer = []
        self._collect_buffer_ts = []
        self._collect_target_frames = max(1, int(duration_sec * fps))
        self.collection_progress.emit(0.0)

    def _finish_collection(self) -> None:
        mode = self._collect_mode
        frames = self._collect_buffer
        frame_timestamps = self._collect_buffer_ts
        self._collect_buffer = []
        self._collect_buffer_ts = []

        if mode == "mask":
            self.detect_valid_mask(frames)
        elif mode == "zero":
            self._finish_zero_calibration(frames)
        elif mode == "point":
            self._finish_point_collection(frames, frame_timestamps)

    def _compute_zone_avg_adc(
        self, frames: list[np.ndarray], zone: FootZone
    ) -> tuple[float, float, int]:
        """跨帧计算某分区的 avg_ADC 均值、标准差和有效传感器数。"""
        per_frame_avgs: list[float] = []
        valid_counts: list[int] = []

        use_mask = self._valid_mask is not None
        if use_mask:
            mask_region = self._valid_mask[zone.row_start : zone.row_end + 1, :]
            if not np.any(mask_region):
                use_mask = False
                logger.warning(
                    "Zone '%s' has 0 valid sensors in mask, ignoring mask for ADC computation",
                    zone.name,
                )

        for frame in frames:
            region = frame[zone.row_start : zone.row_end + 1, :]

            if use_mask:
                region = np.where(mask_region, region, 0)

            valid = region[region >= self._noise_threshold]
            count = int(valid.size)
            if count > 0:
                per_frame_avgs.append(float(np.sum(valid)) / count)
                valid_counts.append(count)

        if not per_frame_avgs:
            return 0.0, 0.0, 0

        avg_array = np.array(per_frame_avgs)
        return (
            float(np.mean(avg_array)),
            float(np.std(avg_array)),
            int(np.median(valid_counts)),
        )

    def _compute_zone_frame_avg_adc(self, frame: np.ndarray, zone: FootZone) -> float:
        region = frame[zone.row_start : zone.row_end + 1, :]

        if self._valid_mask is not None:
            mask_region = self._valid_mask[zone.row_start : zone.row_end + 1, :]
            if np.any(mask_region):
                region = np.where(mask_region, region, 0)

        valid = region[region >= self._noise_threshold]
        count = int(valid.size)
        if count <= 0:
            return 0.0
        return float(np.sum(valid)) / count

    def _finish_zero_calibration(self, frames: list[np.ndarray]) -> None:
        self._zone_zero_offsets = {}

        for zone in self._zones:
            mean_avg, std_avg, _ = self._compute_zone_avg_adc(frames, zone)
            self._zone_zero_offsets[zone.name] = mean_avg

            self._zone_data_points.setdefault(zone.name, [])
            # 零点: 减去偏移后 ADC 为 0
            zero_point = CalibrationPoint(
                pressure_kpa=0.0,
                avg_adc=0.0,
                adc_std=std_avg,
                sample_count=len(frames),
            )
            existing = self._zone_data_points[zone.name]
            if existing and existing[0].pressure_kpa == 0.0:
                existing[0] = zero_point
            else:
                existing.insert(0, zero_point)

            logger.info(
                "Zone '%s' zero offset: %.2f (std: %.2f)",
                zone.name,
                mean_avg,
                std_avg,
            )

        self.zero_complete.emit(dict(self._zone_zero_offsets))

    def _finish_point_collection(
        self, frames: list[np.ndarray], frame_timestamps: list[float]
    ) -> None:
        if self._contact_area_cm2 <= 0:
            logger.error("Contact area not set, cannot compute pressure")
            return

        pressure_kpa = self._collect_force_n * 10.0 / self._contact_area_cm2
        zones_to_collect = self._zones
        if self._collect_zone_name:
            zones_to_collect = [z for z in self._zones if z.name == self._collect_zone_name]
            if not zones_to_collect:
                logger.warning("Target zone '%s' not found, skip collection", self._collect_zone_name)
                return

        for zone in zones_to_collect:
            mean_avg, std_avg, _ = self._compute_zone_avg_adc(frames, zone)
            zero_offset = self._zone_zero_offsets.get(zone.name, 0.0)
            adjusted_adc = max(mean_avg - zero_offset, 0.0)

            point = CalibrationPoint(
                pressure_kpa=pressure_kpa,
                avg_adc=adjusted_adc,
                adc_std=std_avg,
                sample_count=len(frames),
                position_label=self._collect_position_label,
                repeat_index=self._collect_repeat_index,
            )
            self._zone_data_points.setdefault(zone.name, []).append(point)
            self.collection_complete.emit(zone.name, point)
            self._append_raw_records_for_zone(
                zone=zone,
                frames=frames,
                frame_timestamps=frame_timestamps,
                pressure_kpa=pressure_kpa,
            )

            logger.info(
                "Zone '%s' point: P=%.2f kPa, ADC=%.2f (std: %.2f)",
                zone.name,
                pressure_kpa,
                adjusted_adc,
                std_avg,
            )

    def _append_raw_records_for_zone(
        self,
        zone: FootZone,
        frames: list[np.ndarray],
        frame_timestamps: list[float],
        pressure_kpa: float,
    ) -> None:
        zero_offset = self._zone_zero_offsets.get(zone.name, 0.0)
        ts_list = frame_timestamps if len(frame_timestamps) == len(frames) else [0.0] * len(frames)
        for idx, (frame, ts) in enumerate(zip(frames, ts_list), start=1):
            avg_adc = max(self._compute_zone_frame_avg_adc(frame, zone) - zero_offset, 0.0)
            matrix_flat = " ".join(str(int(v)) for v in frame.reshape(-1))
            timestamp = (
                datetime.fromtimestamp(float(ts)).isoformat(timespec="milliseconds")
                if ts > 0
                else ""
            )
            self._raw_records.append(
                {
                    "timestamp": timestamp,
                    "zone_name": zone.name,
                    "position_label": self._collect_position_label,
                    "repeat_index": self._collect_repeat_index,
                    "frame_index": idx,
                    "contact_area_cm2": self._contact_area_cm2,
                    "pressure_kpa": pressure_kpa,
                    "avg_adc": avg_adc,
                    "adc_matrix_flat": matrix_flat,
                }
            )


# ======================================================================
# 模块级辅助函数
# ======================================================================


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


def _profile_to_dict(profile: CalibrationProfile) -> dict:
    """将 CalibrationProfile 序列化为可 JSON 化的 dict。"""
    zones_dict: dict[str, dict] = {}
    for name, result in profile.zones.items():
        zones_dict[name] = {
            "zero_offset": result.zero_offset,
            "a": result.a,
            "b": result.b,
            "r_squared": result.r_squared,
            "valid_sensor_count": result.valid_sensor_count,
            "data_points": [
                {
                    "pressure_kpa": pt.pressure_kpa,
                    "avg_adc": pt.avg_adc,
                    "adc_std": pt.adc_std,
                    "sample_count": pt.sample_count,
                    "position_label": pt.position_label,
                    "repeat_index": pt.repeat_index,
                }
                for pt in result.data_points
            ],
        }
    return {
        "version": profile.version,
        "device_id": profile.device_id,
        "contact_area_cm2": profile.contact_area_cm2,
        "noise_threshold": profile.noise_threshold,
        "zone_config": profile.zone_config,
        "zones": zones_dict,
        "created_at": profile.created_at,
    }


def _dict_to_profile(data: dict) -> CalibrationProfile:
    """从 JSON dict 反序列化为 CalibrationProfile。"""
    zones: dict[str, ZoneCalibrationResult] = {}
    for name, zd in data.get("zones", {}).items():
        points = [
            CalibrationPoint(
                pressure_kpa=float(pt["pressure_kpa"]),
                avg_adc=float(pt["avg_adc"]),
                adc_std=float(pt.get("adc_std", 0.0)),
                sample_count=int(pt.get("sample_count", 0)),
                position_label=str(pt.get("position_label", "")),
                repeat_index=int(pt.get("repeat_index", 1)),
            )
            for pt in zd.get("data_points", [])
        ]
        zones[name] = ZoneCalibrationResult(
            zone_name=name,
            zero_offset=float(zd.get("zero_offset", 0.0)),
            a=float(zd.get("a", 1.0)),
            b=float(zd.get("b", 0.0)),
            r_squared=float(zd.get("r_squared", 0.0)),
            valid_sensor_count=int(zd.get("valid_sensor_count", 0)),
            data_points=points,
        )
    return CalibrationProfile(
        version=str(data.get("version", "2.0")),
        device_id=str(data.get("device_id", "")),
        contact_area_cm2=float(data.get("contact_area_cm2", 0.0)),
        noise_threshold=int(data.get("noise_threshold", 10)),
        zone_config=data.get("zone_config", {}),
        zones=zones,
        created_at=str(data.get("created_at", "")),
    )
