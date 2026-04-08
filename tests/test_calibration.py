from __future__ import annotations

import csv

import numpy as np

from config import ADC_COLS, ADC_NOISE_THRESHOLD, ADC_ROWS
from data.calibration_engine import CalibrationEngine
from data.models import CalibrationPoint


def _frame_with_zone_value(zone_row_start: int, zone_row_end: int, value: int) -> np.ndarray:
    frame = np.zeros((ADC_ROWS, ADC_COLS), dtype=np.uint8)
    frame[zone_row_start : zone_row_end + 1, :] = value
    return frame


def test_zero_calibration_filters_noise_threshold() -> None:
    engine = CalibrationEngine()
    engine.start_zero_calibration(duration_sec=1.0, fps=2)

    noisy_heel = _frame_with_zone_value(0, 3, ADC_NOISE_THRESHOLD - 1)
    valid_midfoot = _frame_with_zone_value(4, 7, ADC_NOISE_THRESHOLD + 2)
    engine.feed_frame(noisy_heel)
    engine.feed_frame(valid_midfoot)

    offsets = engine.zone_zero_offsets
    assert offsets["heel"] == 0.0
    assert offsets["midfoot"] > 0.0


def test_point_collection_computes_pressure_and_avg_adc() -> None:
    engine = CalibrationEngine()
    engine.set_contact_area(50.0)

    engine.start_zero_calibration(duration_sec=1.0, fps=1)
    engine.feed_frame(np.zeros((ADC_ROWS, ADC_COLS), dtype=np.uint8))

    engine.start_point_collection(force_n=49.0, duration_sec=1.0, fps=2, zone_name="heel")
    heel_frame = _frame_with_zone_value(0, 3, 30)
    engine.feed_frame(heel_frame)
    engine.feed_frame(heel_frame)

    points = engine.zone_data_points["heel"]
    last_point = points[-1]
    assert abs(last_point.pressure_kpa - 9.8) < 1e-6
    assert abs(last_point.avg_adc - 30.0) < 1e-6


def test_point_collection_weight_kg_backward_compatible() -> None:
    engine = CalibrationEngine()
    engine.set_contact_area(50.0)

    engine.start_zero_calibration(duration_sec=1.0, fps=1)
    engine.feed_frame(np.zeros((ADC_ROWS, ADC_COLS), dtype=np.uint8))

    engine.start_point_collection(weight_kg=5.0, duration_sec=1.0, fps=1, zone_name="heel")
    heel_frame = _frame_with_zone_value(0, 3, 20)
    engine.feed_frame(heel_frame)

    last_point = engine.zone_data_points["heel"][-1]
    assert abs(last_point.pressure_kpa - 9.8) < 1e-6


def test_fit_zone_returns_expected_linear_coefficients_and_r2() -> None:
    engine = CalibrationEngine()
    engine._zone_data_points["heel"] = [
        CalibrationPoint(pressure_kpa=1.0, avg_adc=0.0, adc_std=0.0, sample_count=100),
        CalibrationPoint(pressure_kpa=11.0, avg_adc=5.0, adc_std=0.0, sample_count=100),
        CalibrationPoint(pressure_kpa=21.0, avg_adc=10.0, adc_std=0.0, sample_count=100),
    ]

    result = engine.fit_zone("heel")
    assert result is not None
    assert abs(result.a - 2.0) < 1e-9
    assert abs(result.b - 1.0) < 1e-9
    assert abs(result.r_squared - 1.0) < 1e-9


def test_export_import_json_roundtrip(tmp_path) -> None:
    engine = CalibrationEngine()
    engine.set_contact_area(50.0)
    engine.set_device_id("sensor_0x03")
    engine._zone_data_points["heel"] = [
        CalibrationPoint(pressure_kpa=0.0, avg_adc=0.0, adc_std=0.1, sample_count=50),
        CalibrationPoint(pressure_kpa=9.8, avg_adc=20.0, adc_std=0.2, sample_count=50),
    ]
    engine._zone_zero_offsets["heel"] = 1.2

    output = tmp_path / "calibration_v2.json"
    engine.export_json(str(output))

    profile = CalibrationEngine.import_json(str(output))
    assert profile.version == "2.0"
    assert profile.device_id == "sensor_0x03"
    assert abs(profile.contact_area_cm2 - 50.0) < 1e-9
    assert "heel" in profile.zones
    assert len(profile.zones["heel"].data_points) >= 2


def test_export_raw_csv_contains_per_frame_adc_records(tmp_path) -> None:
    engine = CalibrationEngine()
    engine.set_contact_area(50.0)

    engine.start_zero_calibration(duration_sec=1.0, fps=1)
    engine.feed_frame(np.zeros((ADC_ROWS, ADC_COLS), dtype=np.uint8))

    engine.start_point_collection(
        force_n=49.0,
        duration_sec=1.0,
        fps=2,
        zone_name="heel",
        position_label="center",
        repeat_index=2,
    )
    heel_frame = _frame_with_zone_value(0, 3, 20)
    engine.feed_frame(heel_frame)
    engine.feed_frame(heel_frame)

    raw_csv = tmp_path / "calibration_raw.csv"
    engine.export_raw_csv(str(raw_csv))

    with raw_csv.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 2
    row0 = rows[0]
    assert row0["timestamp"] != ""
    assert row0["zone_name"] == "heel"
    assert row0["position_label"] == "center"
    assert row0["repeat_index"] == "2"
    assert row0["frame_index"] == "1"
    assert abs(float(row0["contact_area_cm2"]) - 50.0) < 1e-9
    assert abs(float(row0["pressure_kpa"]) - 9.8) < 1e-9
    assert row0["adc_matrix_flat"] != ""
