from __future__ import annotations

APP_QSS = """
QMainWindow {
    background-color: #151a22;
    color: #e6edf3;
}

QWidget {
    background-color: #151a22;
    color: #e6edf3;
    font-size: 13px;
}

QLabel {
    color: #d9e1ea;
}

QPushButton {
    background-color: #263447;
    border: 1px solid #32445d;
    border-radius: 6px;
    padding: 6px 10px;
}

QPushButton:hover {
    background-color: #2d3e55;
}

QPushButton:pressed {
    background-color: #223041;
}

QPushButton:disabled {
    background-color: #1f2734;
    color: #7f8b99;
    border-color: #2a3444;
}

QLineEdit,
QComboBox,
QSpinBox,
QDoubleSpinBox {
    background-color: #0f141b;
    border: 1px solid #2f3d4f;
    border-radius: 6px;
    padding: 5px 8px;
    selection-background-color: #2f81f7;
}

QGroupBox {
    border: 1px solid #2e3f54;
    border-radius: 8px;
    margin-top: 10px;
    padding-top: 8px;
    background-color: #1a2230;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #8cb4ff;
}

QDockWidget {
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
}

QDockWidget::title {
    background-color: #1b2533;
    color: #dce6f2;
    padding: 6px 8px;
    border-bottom: 1px solid #2f4056;
}

QMenuBar {
    background-color: #10151d;
    border-bottom: 1px solid #2c3a4c;
}

QMenuBar::item {
    background-color: transparent;
    padding: 6px 10px;
}

QMenuBar::item:selected {
    background-color: #223041;
}

QMenu {
    background-color: #10151d;
    border: 1px solid #2d3d51;
}

QMenu::item {
    padding: 6px 20px;
}

QMenu::item:selected {
    background-color: #263447;
}

QStatusBar {
    background-color: #10151d;
    border-top: 1px solid #2c3a4c;
    color: #b8c3cf;
}

QToolTip {
    background-color: #0f141b;
    color: #e6edf3;
    border: 1px solid #3a4d66;
    padding: 4px 6px;
}

QComboBox::drop-down {
    border: 0px;
    width: 24px;
}

QComboBox QAbstractItemView {
    background-color: #10151d;
    border: 1px solid #2d3d51;
    selection-background-color: #2f81f7;
    selection-color: #ffffff;
}

QProgressBar {
    border: 1px solid #2f3d4f;
    border-radius: 6px;
    background-color: #0f141b;
    text-align: center;
}

QProgressBar::chunk {
    background-color: #2f81f7;
    border-radius: 6px;
}
"""
