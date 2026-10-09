"""Fetch WUSA offers and print their details to the terminal."""

import argparse
import os
from pathlib import Path
import sys
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

OFFERS_URL = "https://member.wusa.ca/your_offers"


def check_login(html, url=OFFERS_URL):
    soup = BeautifulSoup(html, "html.parser")
    if urlparse(url).path.rstrip("/") in {"/login", "/users/sign_in"} or soup.select_one(
        'a[href="/users/auth/saml"], form[action="/users/sign_in"]'
    ):
        raise ValueError(
            "WUSA requires sign-in. Run python Scraperpy.py --login and sign in "
            "in the browser, or set WUSA_COOKIE to your existing session cookie."
        )


def parse_offers(html, selector=None):
    """Extract table rows or offer cards, preserving all displayed details."""
    check_login(html)
    soup = BeautifulSoup(html, "html.parser")
    for element in soup.select("nav, footer, script, style, #breadcrumbs"):
        element.decompose()
    content = soup.select_one("main") or soup
    offers = []

    def add_offer(title, details, element):
        links = list(dict.fromkeys(
            urljoin(OFFERS_URL, a["href"])
            for a in element.select("a[href]")
            if a["href"] and not a["href"].startswith(("#", "javascript:", "mailto:"))
            and urlparse(urljoin(OFFERS_URL, a["href"])).scheme in {"http", "https"}
        ))
        offer = {"title": title, "details": details, "links": links}
        if title and offer not in offers:
            offers.append(offer)

    if not selector:
        for table in content.select("table"):
            headers = [th.get_text(" ", strip=True) for th in table.select("thead th")]
            if not headers:
                first_row = table.find("tr")
                headers = [th.get_text(" ", strip=True) for th in first_row.find_all("th")] if first_row else []
            for row in table.select("tr"):
                cells = row.find_all("td", recursive=False)
                values = [cell.get_text(" ", strip=True) for cell in cells]
                if not any(values):
                    continue
                details = [
                    f"{headers[i]}: {value}" if i < len(headers) and headers[i] else value
                    for i, value in enumerate(values) if value
                ]
                add_offer(next(value for value in values if value), details, row)
        if offers:
            return offers

    cards = content.select(selector or ".offer, .offer-card, .card, article")
    for card in cards:
        # Only parse the innermost card when wrappers also match.
        if any(other is not card and card in other.parents for other in cards):
            continue
        heading = card.select_one("h2, h3, h4, h5, h6, .card-title, .offer-title")
        lines = list(dict.fromkeys(card.stripped_strings))
        if not lines:
            continue
        title = heading.get_text(" ", strip=True) if heading else lines[0]
        add_offer(title, [line for line in lines if line != title], card)

    if not offers:
        raise ValueError(
            "No offer tables or cards were found. The page may be empty or its "
            "layout may have changed. Use --selector with the CSS selector "
            "for each offer on the page."
        )
    return offers


def get_offers(cookie=None, selector=None):
    headers = {"User-Agent": "Mozilla/5.0"}
    if cookie:
        headers["Cookie"] = cookie
    response = requests.get(OFFERS_URL, headers=headers, timeout=30)
    response.raise_for_status()
    check_login(response.text, response.url)
    return parse_offers(response.text, selector)


def get_offers_with_login(selector=None):
    """Let the user authenticate directly with Waterloo in a temporary browser."""
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ValueError(
            "Install browser support: python -m pip install playwright, "
            "then python -m playwright install chromium"
        ) from exc

    with sync_playwright() as playwright:
        browser = None
        try:
            browser = playwright.chromium.launch(headless=False)
            page = browser.new_page()
            page.goto(OFFERS_URL, wait_until="domcontentloaded", timeout=60000)
            input("Sign in in the browser. When your offers are visible, press Enter here: ")
            page.goto(OFFERS_URL, wait_until="domcontentloaded", timeout=60000)
            check_login(page.content(), page.url)
            try:
                page.locator(selector or "main table, main .offer, main .offer-card, main .card, main article").first.wait_for(timeout=10000)
            except PlaywrightTimeoutError:
                pass  # parse_offers provides the more useful layout/empty-page error.
            return parse_offers(page.content(), selector)
        except PlaywrightError as exc:
            raise ValueError(
                f"Browser error: {exc}\nIf Chromium is missing, run "
                "python -m playwright install chromium."
            ) from exc
        finally:
            if browser is not None:
                browser.close()


def print_offers(offers):
    print(f"Found {len(offers)} offer(s).\n")
    for number, offer in enumerate(offers, start=1):
        print(f"{number}. {offer['title']}")
        for detail in offer["details"]:
            print(f"   {detail}")
        for link in offer["links"]:
            print(f"   Link: {link}")
        print()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--login", action="store_true", help="Open a browser for manual Waterloo sign-in")
    source.add_argument("--html", type=Path, help="Parse an already saved offers HTML file offline")
    parser.add_argument("--selector", help="CSS selector matching each offer card")
    args = parser.parse_args()
    try:
        if args.html:
            offers = parse_offers(args.html.read_text(encoding="utf-8"), args.selector)
        elif args.login:
            offers = get_offers_with_login(args.selector)
        else:
            offers = get_offers(os.environ.get("WUSA_COOKIE"), args.selector)
        print_offers(offers)
    except (requests.RequestException, OSError, ValueError, EOFError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
