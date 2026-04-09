from __future__ import annotations

import numpy as np

from config import ADC_ROWS
from data.data_processor import DataProcessor
from data.models import CalibrationProfile, ZoneCalibrationResult
from ui.heatmap_view import _sigma_for_canvas_rows


def test_zone_calibration_preserves_toe_shape_while_scaling_pressure() -> None:
    processor = DataProcessor()
    processor.set_calibration(
        CalibrationProfile(
            zones={
                "toes": ZoneCalibrationResult(
                    zone_name="toes",
                    zero_offset=0.0,
                    a=2.0,
                    b=0.0,
                    r_squared=1.0,
                    valid_sensor_count=3,
                )
            }
        )
    )

    adc_data = np.zeros((ADC_ROWS, ADC_COLS), dtype=np.float64)
    adc_data[12, 2] = 10.0
    adc_data[12, 4] = 20.0
    adc_data[13, 5] = 40.0
    zone_metrics = processor._compute_zone_metrics(adc_data.astype(np.uint8))

    calibrated = processor._apply_calibration(adc_data, zone_metrics)

    assert np.allclose(calibrated[12, 2], 20.0)
    assert np.allclose(calibrated[12, 4], 40.0)
    assert np.allclose(calibrated[13, 5], 80.0)
    assert np.count_nonzero(calibrated) == 3
    assert np.allclose(zone_metrics["toes"].pressure_kpa, 46.666666666666664)


def test_toe_rows_use_tighter_heatmap_sigma_than_midfoot_rows() -> None:
    sigma = _sigma_for_canvas_rows(np.array([7.5, 12.0, 13.5], dtype=np.float64))

    assert sigma[0] > sigma[1]
    assert sigma[1] >= sigma[2]
