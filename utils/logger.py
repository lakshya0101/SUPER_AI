"""Central logging configuration for the automation framework."""

import logging
from pathlib import Path

from config.settings import REPORTS_DIR


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger instance."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    log_file = Path(REPORTS_DIR) / "automation.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    return logger
