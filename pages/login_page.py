"""Page object for the Super AI login page."""

from playwright.sync_api import Page

from config.settings import DEFAULT_TIMEOUT, SUPER_AI_URL
from utils.logger import get_logger


class LoginPageLocators:
    """Locators for the Super AI login page."""

    WORK_EMAIL_INPUT = 'input[type="email"]'
    MICROSOFT_LOGIN_BUTTON = 'button:has-text("Sign In with Microsoft")'


class LoginPage:
    """Actions available on the Super AI login page."""

    def __init__(self, page: Page) -> None:
        self.page = page
        self.logger = get_logger(self.__class__.__name__)

    def open(self) -> None:
        """Open the Super AI login URL."""
        self.logger.info("Navigating to Super AI login URL")
        self.page.goto(SUPER_AI_URL, timeout=DEFAULT_TIMEOUT)
        self.page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT)

    def enter_email(self, email: str) -> None:
        """Enter work email on the Super AI login page."""
        self.logger.info("Entering work email")
        self.page.wait_for_selector(
            LoginPageLocators.WORK_EMAIL_INPUT,
            timeout=DEFAULT_TIMEOUT,
        )
        self.page.fill(LoginPageLocators.WORK_EMAIL_INPUT, email)

    def click_microsoft_login(self) -> None:
        """Click the Sign In with Microsoft button."""
        self.logger.info("Clicking Sign In with Microsoft")
        self.page.click(LoginPageLocators.MICROSOFT_LOGIN_BUTTON)
