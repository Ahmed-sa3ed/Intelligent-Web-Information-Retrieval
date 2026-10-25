from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from forms import parse_search_forms  # NEW
from tables import format_simple_tables


class UnsupportedContentTypeError(ValueError):
    """A downloaded link points to content this HTML agent cannot read."""


def fetch_page(url: str) -> dict:
    """Fetch an HTML page and return its text, links, and search forms."""
    if urlsplit(url).scheme not in {"http", "https"}:
        raise ValueError("Only HTTP and HTTPS URLs are supported.")

    response = httpx.get(
        url,
        follow_redirects=True,
        timeout=10,
    )
    response.raise_for_status()

    content_type = response.headers.get("content-type", "").lower()
    if "text/html" not in content_type:
        raise UnsupportedContentTypeError(f"Expected HTML, received: {content_type}")

    # NEW: inspect the downloaded HTML before reducing it to page text.
    forms = parse_search_forms(response.text, str(response.url))

    soup = BeautifulSoup(response.text, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""

    for element in soup.select("script, style, template"):
        element.decompose()

    links = []
    seen = set()
    content_anchors = soup.select("main a[href], article a[href]")
    for anchor in content_anchors + soup.select("a[href]"):
        target = urljoin(str(response.url), anchor["href"])
        if urlsplit(target).scheme not in {"http", "https"}:
            continue
        if target in seen:
            continue
        seen.add(target)
        links.append({
            "text": anchor.get_text(" ", strip=True),
            "url": target,
        })

    table_rows = format_simple_tables(soup)
    text = soup.get_text("\n", strip=True)

    # Put labeled table rows where the model sees them early.
    # Limit this prefix so ordinary page text still has room.
    promoted = []
    size = 0
    for row in table_rows:
        if size + len(row) + 1 > 4000:
            break
        promoted.append(row)
        size += len(row) + 1
    if promoted:
        text = "\n".join(promoted) + "\n\n" + text
    return {
        "url": str(response.url),
        "title": title,
        "text": text,
        "text_truncated": False,
        "links": links,
        "links_truncated": False,
        "forms": forms,  # NEW
    }
