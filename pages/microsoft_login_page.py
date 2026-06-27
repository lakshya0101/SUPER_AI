"""Page object for Microsoft SSO login."""

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from config.settings import DEFAULT_TIMEOUT, SHORT_TIMEOUT
from utils.logger import get_logger


class MicrosoftLoginPageLocators:
    """Locators for Microsoft login pages and prompts."""

    EMAIL_INPUT = 'input[type="email"]'
    PASSWORD_INPUT = 'input[type="password"]'
    SUBMIT_BUTTON = 'input[type="submit"]'


class MicrosoftLoginPage:
    """Actions available on Microsoft SSO pages."""

    def __init__(self, page: Page) -> None:
        self.page = page
        self.logger = get_logger(self.__class__.__name__)

    def enter_username(self, username: str) -> None:
        """Enter Microsoft username when the field is available."""
        self.logger.info("Entering Microsoft username")
        self._wait_for_email_or_password_screen()

        if self.page.locator(MicrosoftLoginPageLocators.PASSWORD_INPUT).is_visible():
            self.logger.info("Microsoft username already accepted")
            return

        try:
            self.page.fill(MicrosoftLoginPageLocators.EMAIL_INPUT, username)
        except Exception as exc:
            self.logger.info("Microsoft username was already populated: %s", exc)

    def _wait_for_email_or_password_screen(self) -> None:
        """Wait until Microsoft displays either username or password screen."""
        self.page.wait_for_function(
            """
            () => {
                const email = document.querySelector('input[type="email"]');
                const password = document.querySelector('input[type="password"]');
                const isVisible = element => {
                    if (!element) return false;
                    const style = window.getComputedStyle(element);
                    return style.visibility !== 'hidden'
                        && style.display !== 'none'
                        && element.getClientRects().length > 0;
                };
                return isVisible(email) || isVisible(password);
            }
            """,
            timeout=DEFAULT_TIMEOUT,
        )

    def is_password_screen_visible(self) -> bool:
        """Return whether the Microsoft password screen is visible."""
        return self.page.locator(MicrosoftLoginPageLocators.PASSWORD_INPUT).is_visible()

    def enter_password(self, password: str) -> None:
        """Enter Microsoft password."""
        self.logger.info("Entering Microsoft password")
        self.page.wait_for_selector(
            MicrosoftLoginPageLocators.PASSWORD_INPUT,
            timeout=DEFAULT_TIMEOUT,
        )
        self.page.fill(MicrosoftLoginPageLocators.PASSWORD_INPUT, password)

    def click_next(self) -> None:
        """Submit the active Microsoft form."""
        self.logger.info("Submitting Microsoft login form")
        self.page.click(MicrosoftLoginPageLocators.SUBMIT_BUTTON)

    def handle_stay_signed_in(self) -> None:
        """Handle the optional Stay Signed In prompt."""
        self.logger.info("Checking for Stay Signed In prompt")

        try:
            self.page.wait_for_selector(
                MicrosoftLoginPageLocators.SUBMIT_BUTTON,
                timeout=SHORT_TIMEOUT,
            )

            if self.page.locator(MicrosoftLoginPageLocators.SUBMIT_BUTTON).count() > 0:
                self.logger.info("Accepting Stay Signed In prompt")
                self.page.click(MicrosoftLoginPageLocators.SUBMIT_BUTTON)

        except PlaywrightTimeoutError:
            self.logger.info("Stay Signed In prompt was not displayed")
        except PlaywrightError as exc:
            if "Target page, context or browser has been closed" in str(exc):
                self.logger.info("Microsoft SSO closed the login page during redirect.")
                return
            raise
