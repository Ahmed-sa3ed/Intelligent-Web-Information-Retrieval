"""Scrapling HTTP retrieval compatible with the existing agent page contract.

The browser fetcher is deliberately excluded from this first comparison: it
would add rendering, hardware cost and site behavior the baseline does not have.
"""
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup
from scrapling.fetchers import Fetcher

from forms import parse_search_forms
from tables import format_simple_tables
from retrieval import UnsupportedContentTypeError


def fetch_page(url: str) -> dict:
    if urlsplit(url).scheme not in {"http", "https"}:
        raise ValueError("Only HTTP and HTTPS URLs are supported.")
    request = httpx.Request("GET", url)
    try:
        response = Fetcher.get(
            url, follow_redirects=True, timeout=10, retries=1,
            stealthy_headers=False, impersonate=None, verify=True,
        )
    except Exception as exc:
        # The agent already treats httpx network failures as recoverable.
        raise httpx.RequestError(str(exc), request=request) from exc

    if not 200 <= response.status < 300:
        raise httpx.HTTPStatusError(
            f"HTTP {response.status} for {url}", request=request,
            response=httpx.Response(response.status, request=request),
        )
    content_type = next(
        (value for key, value in response.headers.items()
         if key.lower() == "content-type"), ""
    ).lower()
    if "text/html" not in content_type:
        raise UnsupportedContentTypeError(f"Expected HTML, received: {content_type}")

    final_url = str(response.url)
    html = response.body.decode(response.encoding or "utf-8", errors="replace")
    forms = parse_search_forms(html, final_url)

    # Scrapling parses the title, links and visible text. Keep the established
    # table formatter, so the two versions differ in retrieval and DOM parsing
    # while sharing the same evidence and answer logic.
    title = str(response.css("title::text").get() or "").strip()
    links, seen = [], set()
    content_anchors = response.css("main a[href], article a[href]")
    for anchor in list(content_anchors) + list(response.css("a[href]")):
        target = urljoin(final_url, str(anchor.attrib.get("href", "")))
        if urlsplit(target).scheme not in {"http", "https"} or target in seen:
            continue
        seen.add(target)
        links.append({
            "text": str(anchor.get_all_text(separator=" ", strip=True)),
            "url": target,
        })

    soup = BeautifulSoup(html, "html.parser")
    for element in soup.select("script, style, template"):
        element.decompose()
    table_rows = format_simple_tables(soup)
    text = str(response.get_all_text(
        separator="\n", strip=True,
        ignore_tags=("script", "style", "template"),
    ))
    promoted, size = [], 0
    for row in table_rows:
        if size + len(row) + 1 > 4000:
            break
        promoted.append(row)
        size += len(row) + 1
    if promoted:
        text = "\n".join(promoted) + "\n\n" + text
    return {
        "url": final_url,
        "title": title,
        "text": text,
        "text_truncated": False,
        "links": links,
        "links_truncated": False,
        "forms": forms,
    }
