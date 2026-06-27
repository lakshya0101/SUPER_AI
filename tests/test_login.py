"""Login test for Super AI using Page Object Model classes."""

from utils.browser_manager import BrowserManager
from utils.helpers import capture_screenshot
from utils.login_flow import login_to_super_ai
from utils.logger import get_logger


def test_super_ai_login() -> None:
    """Launch browser, execute Microsoft SSO login, verify login, and close."""
    logger = get_logger("test_super_ai_login")
    browser_manager = BrowserManager()
    page = None

    try:
        page = browser_manager.launch_browser()
        super_ai_page = login_to_super_ai(page)

        assert super_ai_page.verify_login()
        logger.info("Login success")

    except Exception as exc:
        logger.exception("Login test failed: %s", exc)

        if page:
            screenshot_path = capture_screenshot(page, "login_failure")
            logger.error("Failure screenshot captured: %s", screenshot_path)

        raise

    finally:
        browser_manager.close_browser()
