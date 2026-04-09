from __future__ import annotations

from pathlib import Path


APP_NAME = "Smart Insole Collector"
APP_VERSION = "0.1.0"

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
CALIBRATION_DIR = BASE_DIR / "calibration_files"

SERIAL_BAUDRATE = 921600
SERIAL_BYTESIZE = 8
SERIAL_PARITY = "N"
SERIAL_STOPBITS = 1

FRAME_HEADER = bytes([0xAA, 0x55, 0x03, 0x99])
PACK1_SEQ = 0x01
PACK2_SEQ = 0x02
PACK1_DATA_LEN = 128
PACK2_DATA_LEN = 144
MERGED_DATA_LEN = PACK1_DATA_LEN + PACK2_DATA_LEN

UI_REFRESH_FPS = 30
UI_REFRESH_INTERVAL_MS = int(1000 / UI_REFRESH_FPS)

# ADC 噪声过滤阈值：小于该值视为杂信号
ADC_NOISE_THRESHOLD = 10

# ADC 空间映射配置（右脚鞋垫）
# 物理传感器阵列为 16行×8列（14有效行+2填充，8列=内外侧）。
# 128 字节按行优先 reshape(16, 8) 后翻转对齐足底方位。
ADC_ROWS = 16
ADC_COLS = 8
ADC_USE_HIGH_HALF = False
ADC_FLIP_LEFT_RIGHT = True
ADC_FLIP_UP_DOWN = True

# 默认足底分区（16×8 阵列，按行划分 4 区；行方向=前后轴）
DEFAULT_FOOT_ZONES = (
    {"name": "heel", "display_name": "后跟区", "row_start": 0, "row_end": 3},
    {"name": "midfoot", "display_name": "足弓区", "row_start": 4, "row_end": 7},
    {"name": "forefoot", "display_name": "前掌区", "row_start": 8, "row_end": 11},
    {"name": "toes", "display_name": "脚趾区", "row_start": 12, "row_end": 15},
)

# 热力图上采样倍率（16×8 → 160×80，使色彩过渡更平滑）
HEATMAP_UPSAMPLE = 10
HEATMAP_RBF_SIGMA = 1.0
HEATMAP_TOE_RBF_SIGMA = 0.55
HEATMAP_TOE_TRANSITION_ROWS = 1.0
HEATMAP_TOE_ROW_START = next(
    int(zone["row_start"])
    for zone in DEFAULT_FOOT_ZONES
    if str(zone["name"]) == "toes"
)

# 右脚鞋垫轮廓控制点（显示坐标：x=0..8 列方向, y=0..16 行方向）
# y=0 后跟（底部）, y=16 脚趾（顶部）
# x=0 内侧（大趾侧，足弓凹陷）, x=8 外侧（小趾侧）
# 基于 JQGY-YL-668 规格书（279×171mm, 传感面积 243×70mm）设计
INSOLE_CONTOUR_RIGHT: list[tuple[float, float]] = [
    # ── 后跟底部（圆弧） ──
    (4.20, -0.15),
    (4.90, -0.10),
    (5.60, 0.10),
    (6.15, 0.45),
    (6.60, 0.95),
    (6.90, 1.60),
    (7.10, 2.40),
    # ── 外侧：后跟→足弓 ──
    (7.28, 3.20),
    (7.38, 3.90),
    # ── 外侧足弓（轻微外凸） ──
    (7.35, 4.70),
    (7.28, 5.40),
    (7.28, 6.10),
    (7.42, 6.90),
    (7.62, 7.70),
    # ── 外侧前掌（最宽处） ──
    (7.82, 8.50),
    (7.94, 9.30),
    (8.00, 10.10),
    (8.00, 10.90),
    # ── 外侧前足→脚趾 ──
    (7.92, 11.50),
    (7.72, 12.10),
    (7.48, 12.70),
    (7.15, 13.30),
    # ── 脚趾区（小趾→大趾） ──
    (6.80, 13.85),
    (6.40, 14.30),
    (6.00, 14.70),
    (5.60, 15.00),
    (5.15, 15.30),
    (4.65, 15.60),
    (4.15, 15.85),
    (3.65, 16.03),
    (3.15, 16.13),
    (2.70, 16.08),
    (2.25, 15.88),
    (1.85, 15.52),
    (1.50, 15.08),
    (1.18, 14.50),
    (0.92, 13.85),
    # ── 内侧前掌 ──
    (0.70, 13.10),
    (0.50, 12.30),
    (0.36, 11.50),
    (0.28, 10.70),
    # ── 内侧前掌→足弓过渡 ──
    (0.35, 9.95),
    (0.60, 9.25),
    (0.98, 8.55),
    (1.42, 7.95),
    # ── 内侧足弓（凹陷，鞋垫最窄处） ──
    (1.90, 7.35),
    (2.28, 6.75),
    (2.58, 6.05),
    (2.72, 5.35),
    (2.72, 4.65),
    (2.58, 3.95),
    # ── 内侧足弓→后跟 ──
    (2.32, 3.25),
    (2.05, 2.55),
    (1.92, 1.85),
    (2.02, 1.25),
    (2.30, 0.65),
    (2.72, 0.28),
    (3.28, 0.00),
    (3.80, -0.15),
]

# 标定采样建议参数
CALIBRATION_DEFAULT_DURATION_SEC = 3.0
CALIBRATION_DEFAULT_WEIGHTS_KG = (0.0, 1.0, 2.0, 5.0, 10.0, 20.0)


def build_logging_config() -> dict:
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "level": "INFO",
            },
            "app_file": {
                "class": "logging.FileHandler",
                "formatter": "default",
                "level": "DEBUG",
                "filename": str(LOG_DIR / "app.log"),
                "encoding": "utf-8",
            },
            "comm_file": {
                "class": "logging.FileHandler",
                "formatter": "default",
                "level": "DEBUG",
                "filename": str(LOG_DIR / "comm.log"),
                "encoding": "utf-8",
            },
        },
        "loggers": {
            "comm": {
                "handlers": ["console", "comm_file"],
                "level": "DEBUG",
                "propagate": False,
            }
        },
        "root": {
            "handlers": ["console", "app_file"],
            "level": "INFO",
        },
    }
