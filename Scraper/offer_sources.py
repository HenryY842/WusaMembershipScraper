"""Read bounded offer webpages and posters without forwarding WUSA credentials."""

from collections import deque
import ipaddress
import json
import re
import socket
import time
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup
import requests

MAX_SOURCES = 8
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_TOTAL_BYTES = 12 * 1024 * 1024
MAX_TEXT_CHARS = 18000
MAX_OFFER_SECONDS = 90
MEDIA_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/webp", "image/heic", "image/heif"}
LOCATION_LINK = re.compile(r"contact|location|find.us|visit.us|store.locator|where.to.find", re.I)
DOCUMENT_LINK = re.compile(r"\.(pdf|png|jpe?g|webp)(?:$|[?#])|download_file", re.I)


def public_url(url):
    """Validate each target, including redirects, before making a request."""
    parts = urlsplit(url)
    if (parts.scheme not in {"http", "https"} or not parts.hostname
            or parts.username or parts.password or parts.port not in {None, 80, 443}):
        raise ValueError("Unsupported URL")
    addresses = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80), type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError("Non-public URL")
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


def display_url(url):
    parts = urlsplit(url)
    # Do not expose login/download tokens in Gemini prompts or source metadata.
    return urlunsplit((parts.scheme, parts.hostname or "", parts.path, "", ""))


def is_wusa(url):
    parts = urlsplit(url)
    return parts.scheme == "https" and parts.hostname == "member.wusa.ca" and parts.port in {None, 443}


class OfferSourceReader:
    def __init__(self, headers=None, cookies=None):
        headers = requests.structures.CaseInsensitiveDict(headers or {})
        self.headers = {name: headers[name] for name in ("Cookie", "Authorization") if name in headers}
        self.cookies = cookies or {}

    def download(self, url, byte_limit=MAX_FILE_BYTES, deadline=None):
        """Stream a small public resource; check credentials again at each redirect."""
        with requests.Session() as session:
            # Do not acquire unrelated .netrc credentials or environment proxies.
            session.trust_env = False
            for _ in range(6):
                url = public_url(url)
                if deadline is not None and time.monotonic() >= deadline:
                    raise ValueError("Offer download time limit exceeded")
                headers = {"User-Agent": "WusaMembershipScraper/1.0", "Accept": "text/html,application/pdf,image/*;q=0.9,*/*;q=0.5"}
                if is_wusa(url):
                    headers.update(self.headers)
                session.cookies.clear()
                with session.get(url, headers=headers, cookies=self.cookies if is_wusa(url) else {},
                                 timeout=(8, 15), stream=True, allow_redirects=False) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("Location")
                        if not location:
                            raise ValueError("Redirect without a destination")
                        url = urljoin(url, location)
                        continue
                    response.raise_for_status()
                    data = bytearray()
                    for chunk in response.iter_content(65536):
                        if deadline is not None and time.monotonic() >= deadline:
                            raise ValueError("Offer download time limit exceeded")
                        data.extend(chunk)
                        if len(data) > byte_limit:
                            raise ValueError("Source exceeds download size limit")
                    mime = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                    return url, mime, bytes(data)
            raise ValueError("Too many redirects")

    def collect(self, offer):
        """Return source text, inline media, and completeness for one offer."""
        pending = deque((url, 0) for url in offer.get("links", []))
        seen = set()
        sources, media = [], []
        total = 0
        deadline = time.monotonic() + MAX_OFFER_SECONDS
        while pending and len(sources) < MAX_SOURCES:
            url, depth = pending.popleft()
            if url in seen:
                continue
            seen.add(url)
            source = {"url": display_url(url), "status": "error"}
            try:
                limit = min(MAX_FILE_BYTES, MAX_TOTAL_BYTES - total)
                if limit <= 0:
                    raise ValueError("Offer download size limit exceeded")
                final_url, mime, data = self.download(url, limit, deadline)
                total += len(data)
                source.update(url=display_url(final_url), content_type=mime)
                # Some download endpoints serve PDFs/images as application/octet-stream.
                if data.startswith(b"%PDF-"):
                    mime = "application/pdf"
                elif data.startswith(b"\x89PNG\r\n\x1a\n"):
                    mime = "image/png"
                elif data.startswith(b"\xff\xd8\xff"):
                    mime = "image/jpeg"
                elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
                    mime = "image/webp"
                source["content_type"] = mime
                if mime in MEDIA_TYPES:
                    media.append({"url": source["url"], "mime_type": mime, "data": data})
                elif mime in {"text/html", "application/xhtml+xml", "text/plain"}:
                    soup = BeautifulSoup(data, "html.parser")
                    if (urlsplit(final_url).path.rstrip("/") in {"/login", "/users/sign_in"}
                            or soup.select_one('a[href="/users/auth/saml"], form[action="/users/sign_in"]')):
                        raise ValueError("Source requires a fresh login")
                    if depth == 0:
                        pending.extend((child, 1) for child in related_links(soup, final_url))
                    addresses = structured_addresses(soup)
                    for tag in soup.select("script, style, noscript, form, input, button"):
                        tag.decompose()
                    source["text"] = (soup.get_text(" ", strip=True)[:MAX_TEXT_CHARS]
                                      + ("\nStructured addresses: " + addresses if addresses else ""))
                    if not source["text"].strip():
                        raise ValueError("Empty page; JavaScript may be required")
                else:
                    raise ValueError("Unsupported source format")
                source["status"] = "ok"
            except (requests.RequestException, ValueError, OSError) as exc:
                # Exception strings can contain signed URLs or credentials.
                source.pop("text", None)
                source["error"] = type(exc).__name__
            sources.append(source)
        # Limits are visible and retryable instead of silently caching incomplete evidence.
        remaining = [url for url, _ in pending if url not in seen]
        if remaining:
            sources.append({"status": "error", "error": "SourceLimit", "skipped": len(set(remaining))})
        return {"sources": sources, "media": media,
                "complete": all(source["status"] == "ok" for source in sources)}


def related_links(soup, base_url):
    """Read one level of contact/location pages and embedded posters, never actions."""
    found = []
    for tag in soup.select("a[href], img[src], object[data], embed[src]"):
        target = tag.get("href") or tag.get("src") or tag.get("data")
        url = urljoin(base_url, target)
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"}:
            continue
        label = tag.get_text(" ", strip=True) + " " + parts.path
        if re.search(r"redeem|claim|checkout|logout|sign.out|unsubscribe", parts.path, re.I):
            continue
        same_site = parts.hostname == urlsplit(base_url).hostname
        if (tag.name in {"object", "embed"} or
                (tag.name == "img" and not re.search(r"logo|icon|avatar|pixel|tracking", target, re.I)) or
                (tag.name == "a" and DOCUMENT_LINK.search(url)) or
                (tag.name == "a" and same_site and LOCATION_LINK.search(label))):
            found.append(url)
    return list(dict.fromkeys(found))


def structured_addresses(soup):
    addresses = []

    def walk(value):
        if isinstance(value, dict):
            if value.get("@type") == "PostalAddress" or "streetAddress" in value:
                fields = ("streetAddress", "addressLocality", "addressRegion", "postalCode", "addressCountry")
                addresses.append(", ".join(str(value[field]) for field in fields if isinstance(value.get(field), str)))
            elif isinstance(value.get("address"), str):
                addresses.append(value["address"])
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    for script in soup.select('script[type="application/ld+json"]'):
        try:
            walk(json.loads(script.string or ""))
        except (ValueError, RecursionError):
            continue
    return "; ".join(dict.fromkeys(addresses))[:4000]
