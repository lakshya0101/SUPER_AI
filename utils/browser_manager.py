"""Browser lifecycle management for Playwright."""

import os
from pathlib import Path
from shutil import which
from uuid import uuid4

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from config.settings import BROWSER_NAME, EDGE_USER_DATA_DIR, HEADLESS_MODE, SLOW_MO
from utils.logger import get_logger

# When INCOGNITO_MODE=1 the browser is launched without a persistent user-data
# directory — every session starts completely fresh (no saved cookies, no
# shared session storage).  Required for running multiple accounts in parallel.
INCOGNITO_MODE: bool = (
    os.getenv("INCOGNITO_MODE", "0").strip().lower() not in {"0", "false", "no", "off"}
)


class BrowserManager:
    """Manage Playwright, browser, context, and page instances."""

    def __init__(
        self,
        browser_name: str = BROWSER_NAME,
        headless: bool = HEADLESS_MODE,
        slow_mo: int = SLOW_MO,
        incognito: bool = INCOGNITO_MODE,
    ) -> None:
        self.browser_name = browser_name
        self.headless = headless
        self.slow_mo = slow_mo
        self.incognito = incognito
        self.playwright: Playwright | None = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.edge_user_data_dir: Path | None = None
        self.logger = get_logger(self.__class__.__name__)

    def launch_browser(self) -> Page:
        """Launch Microsoft Edge and return a new page."""
        self.logger.info("BROWSER = MICROSOFT EDGE")
        self.logger.info("Launching browser: Microsoft Edge (incognito=%s)", self.incognito)
        self.playwright = sync_playwright().start()

        if self.browser_name.lower() not in {"msedge", "microsoft edge", "edge"}:
            raise ValueError("Only Microsoft Edge is supported for this automation.")

        edge_executable = _get_edge_executable_path()
        self.logger.info("Microsoft Edge executable: %s", edge_executable)

        # Always use a fresh unique user-data directory so each browser starts
        # with no saved sessions or cookies.  When incognito=True the directory
        # is placed under a separate "isolated_runs" folder to make it obvious,
        # but the mechanism is identical — a brand-new empty profile.
        # Note: we intentionally do NOT use --inprivate / InPrivate mode because
        # corporate Microsoft tenants commonly block SSO sign-in from private
        # browsing contexts, which causes the browser to crash during redirect.
        base = EDGE_USER_DATA_DIR / ("isolated_runs" if self.incognito else "runs")
        base.mkdir(parents=True, exist_ok=True)
        self.edge_user_data_dir = base / f"run_{uuid4().hex}"
        self.edge_user_data_dir.mkdir(parents=True, exist_ok=True)
        self.context = self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.edge_user_data_dir),
            channel="msedge",
            headless=self.headless,
            slow_mo=self.slow_mo,
        )
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()

        self.logger.info("Browser launched successfully")
        return self.page

    def close_browser(self) -> None:
        """Close page, context, browser, and Playwright safely."""
        self.logger.info("Closing browser")

        if self.context:
            self.context.close()

        if self.browser:
            self.browser.close()

        if self.playwright:
            self.playwright.stop()

        self.logger.info("Browser closed")


def _get_edge_executable_path() -> str:
    """Return installed Microsoft Edge executable path."""
    executable_from_path = which("msedge")
    if executable_from_path:
        return executable_from_path

    candidate_paths = (
        Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
        Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
    )
    for candidate_path in candidate_paths:
        if candidate_path.exists():
            return str(candidate_path)

    raise RuntimeError("Microsoft Edge executable was not found.")
