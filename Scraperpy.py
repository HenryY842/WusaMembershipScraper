"""Fetch WUSA offers and print their details to the terminal."""

import argparse
import ast
import os
from pathlib import Path
import re
import shlex
import sys
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

OFFERS_URL = "https://member.wusa.ca/your_offers"
OFFERS_API_URL = "https://member.wusa.ca/api/member_offers/your_offers"
PROJECT_DIR = Path(__file__).resolve().parent


def clean_headers(headers):
    """Let requests supply transport headers and request fresh HTML."""
    ignored = {"host", "content-length", "accept-encoding", "if-none-match", "if-modified-since"}
    return requests.structures.CaseInsensitiveDict(
        (name, value) for name, value in headers.items()
        if name.lower() not in ignored and not name.startswith(":")
    )


def load_python_request(path):
    """Read curl.trillworks headers/cookies as literal data, without executing code."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    except SyntaxError as exc:
        raise ValueError("The request file must contain valid Python from curl.trillworks.") from exc
    data = {"headers": {}, "cookies": {}}
    for statement in tree.body:
        if not isinstance(statement, ast.Assign):
            continue
        for target in statement.targets:
            if not isinstance(target, ast.Name) or target.id not in data:
                continue
            try:
                value = ast.literal_eval(statement.value)
            except (ValueError, TypeError, SyntaxError) as exc:
                raise ValueError(f"{target.id} must be a literal Python dictionary.") from exc
            if not isinstance(value, dict) or not all(
                isinstance(key, str) and isinstance(item, str)
                and "\n" not in key + item and "\r" not in key + item
                for key, item in value.items()
            ):
                raise ValueError(f"{target.id} must contain string names and values without newlines.")
            data[target.id] = value
    return clean_headers(data["headers"]), data["cookies"]


def load_curl_request(path):
    """Read headers from 'Copy as cURL (bash)'; never run the command."""
    command = re.sub(r"\\\r?\n", " ", path.read_text(encoding="utf-8-sig"))
    tokens = shlex.split(command)
    if not tokens or tokens[0] not in {"curl", "curl.exe"}:
        raise ValueError("The cURL file must start with curl. Use Copy as cURL (bash).")
    headers = {}
    index = 1
    while index < len(tokens):
        token = tokens[index]
        option, separator, attached = token.partition("=")
        if option in {"-H", "--header", "-b", "--cookie", "-X", "--request"}:
            if separator:
                value = attached
            else:
                index += 1
                if index >= len(tokens):
                    raise ValueError("A cURL header, cookie, or method is missing its value.")
                value = tokens[index]
            if option in {"-H", "--header"}:
                name, colon, content = value.partition(":")
                if not colon or not name.strip() or "\n" in value or "\r" in value:
                    raise ValueError("Invalid cURL header. Copy the offers GET request again.")
                headers[name.strip()] = content.strip()
            elif option in {"-b", "--cookie"}:
                if "=" not in value or "\n" in value or "\r" in value:
                    raise ValueError("Use literal cookies from your copied browser request.")
                headers["Cookie"] = value
            elif value.upper() != "GET":
                raise ValueError("Copy the GET request for the offers page.")
        elif option.startswith("--data") or option in {"-d", "-F", "--form", "-I", "--head"}:
            raise ValueError("Copy the GET request for the offers page.")
        index += 1
    return clean_headers(headers), {}


def check_login(html, url=OFFERS_URL):
    soup = BeautifulSoup(html, "html.parser")
    if urlparse(url).path.rstrip("/") in {"/login", "/users/sign_in"} or soup.select_one(
        'a[href="/users/auth/saml"], form[action="/users/sign_in"]'
    ):
        raise ValueError(
            "WUSA did not accept the session cookies (they may have expired). "
            "Copy a fresh authenticated offers request into request.py or request.curl "
            "and run the scraper again."
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


def parse_api_offers(data):
    """Normalize the JSON used by WUSA's JavaScript offers page."""
    if not isinstance(data, dict) or data.get("success") is not True:
        message = data.get("message") if isinstance(data, dict) else None
        raise ValueError(message or "WUSA could not load offers. Check your session cookies.")
    groups = [data.get("featured_offers", []), data.get("offers", [])]
    if not all(isinstance(group, list) for group in groups):
        raise ValueError("WUSA returned an unexpected offers format.")
    offers = []
    seen = set()
    for group in groups:
        for record in group:
            if not isinstance(record, dict) or not isinstance(record.get("title"), str):
                raise ValueError("WUSA returned an unexpected offer format.")
            key = record.get("id") if record.get("id") is not None else record["title"]
            if key in seen:
                continue
            seen.add(key)
            description = BeautifulSoup(record.get("description") or "", "html.parser")
            details = [line.strip() for line in description.get_text("\n", strip=True).splitlines() if line.strip()]
            if record.get("category_name"):
                details.append(f"Category: {record['category_name']}")
            if record.get("expiration_date"):
                details.append(f"Expires: {record['expiration_date']}")
            if "claimed" in record:
                details.append(f"Claimed: {'Yes' if record['claimed'] else 'No'}")
            urls = [record.get("document_url")] + [a.get("href") for a in description.select("a[href]")]
            links = list(dict.fromkeys(
                urljoin(OFFERS_URL, url) for url in urls
                if isinstance(url, str) and url and urlparse(urljoin(OFFERS_URL, url)).scheme in {"http", "https"}
            ))
            offers.append({"title": record["title"], "details": details, "links": links})
    return offers


def get_offers(cookie=None, selector=None, headers=None, cookies=None):
    headers = clean_headers(headers or {})
    headers.setdefault("User-Agent", "Mozilla/5.0")
    headers["Accept"] = "application/json"
    if cookie:
        headers["Cookie"] = cookie
    if not headers.get("Cookie") and not cookies:
        raise ValueError(
            "No session cookies configured. Save curl.trillworks Python output as "
            "request.py beside this script, save Copy as cURL (bash) as request.curl, "
            "or set WUSA_COOKIE. If you edited request.example.py, save it as request.py."
        )
    response = requests.get(OFFERS_API_URL, headers=headers, cookies=cookies or {}, timeout=30)
    if response.status_code in {401, 403}:
        raise ValueError("WUSA rejected the session cookies. Copy a fresh authenticated request into request.py.")
    response.raise_for_status()
    try:
        data = response.json()
    except ValueError as exc:
        check_login(response.text, response.url)
        raise ValueError("WUSA returned HTML instead of offers JSON. Check your session cookies.") from exc
    return parse_api_offers(data)


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
    source.add_argument("--request-file", type=Path, help="Python output from curl.trillworks (reads headers/cookies only)")
    source.add_argument("--curl-file", type=Path, help="Browser request copied as cURL (bash)")
    source.add_argument("--html", type=Path, help="Parse an already saved offers HTML file offline")
    parser.add_argument("--selector", help="CSS selector for offer cards when parsing --html")
    args = parser.parse_args()
    try:
        if args.html:
            offers = parse_offers(args.html.read_text(encoding="utf-8"), args.selector)
        else:
            headers, cookies = {}, {}
            if args.request_file:
                headers, cookies = load_python_request(args.request_file)
            elif args.curl_file:
                headers, cookies = load_curl_request(args.curl_file)
            elif (PROJECT_DIR / "request.py").is_file():
                headers, cookies = load_python_request(PROJECT_DIR / "request.py")
            elif (PROJECT_DIR / "request.curl").is_file():
                headers, cookies = load_curl_request(PROJECT_DIR / "request.curl")
            offers = get_offers(
                os.environ.get("WUSA_COOKIE"), args.selector, headers=headers, cookies=cookies
            )
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
