"""Reusable helper functions for framework-level operations."""

from datetime import datetime
from pathlib import Path

from playwright.sync_api import Page

from config.settings import SCREENSHOT_DIR


def capture_screenshot(page: Page, name: str) -> Path:
    """Capture a screenshot and return the saved file path."""
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshot_path = SCREENSHOT_DIR / f"{name}_{timestamp}.png"
    if page.is_closed():
        return screenshot_path
    page.screenshot(path=str(screenshot_path), full_page=True)
    return screenshot_path
