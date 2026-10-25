"""Bounded Chromium rendering for sparse script-driven HTML pages."""
from urllib.parse import urlsplit

from retrieval import UnsupportedContentTypeError, parse_page


class BrowserRenderError(RuntimeError):
    """Browser startup or navigation failed; the static page remains usable."""


def render_page(url, static_length):
    if urlsplit(url).scheme not in ("http", "https"):
        raise ValueError("Only HTTP and HTTPS URLs are supported.")
    try:
        from playwright.sync_api import Error, TimeoutError as PlaywrightTimeout, sync_playwright
    except ImportError as exc:
        raise BrowserRenderError(
            "Install requirements-browser.txt and run playwright install chromium."
        ) from exc
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                response = page.goto(url, wait_until="domcontentloaded", timeout=12000)
                if response is None or not response.ok:
                    raise BrowserRenderError("Browser navigation did not return successful HTML.")
                content_type = response.headers.get("content-type", "").lower()
                if "text/html" not in content_type:
                    raise UnsupportedContentTypeError(
                        f"Expected HTML, received: {content_type}"
                    )
                try:
                    page.wait_for_function(
                        "minimum => document.body && document.body.innerText.length > minimum",
                        arg=static_length + 10, timeout=5000,
                    )
                except PlaywrightTimeout:
                    pass
                return parse_page(page.content(), page.url)
            finally:
                browser.close()
    except Error as exc:
        raise BrowserRenderError(str(exc)) from exc
