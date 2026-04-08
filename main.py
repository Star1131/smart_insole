from __future__ import annotations

import logging
import logging.config
import sys
import threading
import traceback

from PySide6.QtWidgets import QApplication, QMessageBox

from config import APP_NAME, APP_VERSION, CALIBRATION_DIR, LOG_DIR, build_logging_config
from ui.main_window import MainWindow
from ui.styles import APP_QSS


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    CALIBRATION_DIR.mkdir(parents=True, exist_ok=True)
    logging.config.dictConfig(build_logging_config())


def install_global_exception_hook() -> None:
    def _handle_exception(exc_type, exc_value, exc_tb) -> None:
        logger = logging.getLogger(__name__)
        logger.error("Unhandled exception", exc_info=(exc_type, exc_value, exc_tb))
        QMessageBox.critical(
            None,
            APP_NAME,
            "程序发生未处理异常，请查看 logs/app.log。\n\n"
            + "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
        )

    sys.excepthook = _handle_exception

    # Python 3.8+：兜底线程内未捕获异常，避免后台线程静默失败。
    def _handle_thread_exception(args: threading.ExceptHookArgs) -> None:
        _handle_exception(args.exc_type, args.exc_value, args.exc_traceback)

    threading.excepthook = _handle_thread_exception


def main() -> int:
    setup_logging()
    install_global_exception_hook()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setStyleSheet(APP_QSS)

    window = MainWindow()
    window.show()

    logging.getLogger(__name__).info("Application started")
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
