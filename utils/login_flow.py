"""Reusable login workflow shared by tests and command-line runs."""

from time import monotonic, sleep

from playwright.sync_api import Page

from config.settings import DEFAULT_TIMEOUT
from config.credentials import PASSWORD, USERNAME
from pages.login_page import LoginPage
from pages.microsoft_login_page import MicrosoftLoginPage
from pages.super_ai_page import SuperAIPage, SuperAIPageLocators


def login_to_super_ai(page: Page) -> SuperAIPage:
    """Execute Super AI Microsoft SSO login and return the app page object."""
    context = page.context
    login_page = LoginPage(page)
    microsoft_login_page = MicrosoftLoginPage(page)

    login_page.open()
    login_page.enter_email(USERNAME)
    login_page.click_microsoft_login()

    microsoft_login_page.enter_username(USERNAME)
    if not microsoft_login_page.is_password_screen_visible():
        microsoft_login_page.click_next()

    microsoft_login_page.enter_password(PASSWORD)
    microsoft_login_page.click_next()
    microsoft_login_page.handle_stay_signed_in()

    active_page = _wait_for_super_ai_app_page(context, page)
    super_ai_page = SuperAIPage(active_page)
    super_ai_page.verify_login()
    return super_ai_page


def _wait_for_super_ai_app_page(context, fallback_page: Page) -> Page:
    """Return an open Edge page that has reached the Super AI chat UI."""
    deadline = monotonic() + (DEFAULT_TIMEOUT / 1000)

    while monotonic() < deadline:
        open_pages = [candidate for candidate in context.pages if not candidate.is_closed()]

        for candidate in reversed(open_pages):
            try:
                if candidate.locator(SuperAIPageLocators.CHAT_INPUT).count() > 0:
                    candidate.bring_to_front()
                    return candidate
            except Exception:
                continue

        sleep(1)

    open_pages = [candidate for candidate in context.pages if not candidate.is_closed()]
    if open_pages:
        return open_pages[-1]
    return fallback_page
