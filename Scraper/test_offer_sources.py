import socket
import unittest
from unittest.mock import MagicMock, Mock, patch

import offer_sources as sources
import Scraperpy as scraper


def response(status=200, mime="text/html", data=b"<p>Hello</p>", location=None):
    value = MagicMock()
    value.__enter__.return_value = value
    value.status_code = status
    value.headers = {"Content-Type": mime}
    if location:
        value.headers["Location"] = location
    value.iter_content.return_value = [data]
    return value


class SourceReaderTests(unittest.TestCase):
    def test_authenticated_download_does_not_forward_credentials_after_redirect(self):
        reader = sources.OfferSourceReader(
            {"Cookie": "session=private", "Authorization": "Bearer private", "X-Csrf-Token": "private"},
            {"session": "private"},
        )
        session = MagicMock()
        session.__enter__.return_value = session
        session.get.side_effect = [
            response(302, location="https://cdn.example.com/poster.pdf?signature=secret"),
            response(mime="application/pdf", data=b"%PDF-test"),
        ]
        with patch.object(sources.requests, "Session", return_value=session), patch.object(sources, "public_url", side_effect=lambda url: url):
            evidence = reader.collect({"links": ["https://member.wusa.ca/member_offers/1/download_file"]})
        first, second = session.get.call_args_list
        self.assertEqual(first.kwargs["headers"]["Cookie"], "session=private")
        self.assertEqual(first.kwargs["cookies"], {"session": "private"})
        self.assertNotIn("X-Csrf-Token", first.kwargs["headers"])
        self.assertNotIn("Cookie", second.kwargs["headers"])
        self.assertNotIn("Authorization", second.kwargs["headers"])
        self.assertEqual(second.kwargs["cookies"], {})
        self.assertFalse(second.kwargs["allow_redirects"])
        self.assertFalse(session.trust_env)
        self.assertEqual(session.cookies.clear.call_count, 2)
        self.assertNotIn("secret", str(evidence["sources"]))
        self.assertTrue(evidence["complete"])
        self.assertEqual(evidence["media"][0]["data"], b"%PDF-test")

    def test_private_destinations_and_credentials_are_rejected(self):
        for address in ("127.0.0.1", "10.0.0.1", "169.254.169.254", "::1"):
            with self.subTest(address=address), patch.object(sources.socket, "getaddrinfo", return_value=[
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))
            ]), self.assertRaises(ValueError):
                sources.public_url("https://example.com/poster")
        for url in ("file:///secret", "https://user:password@example.com/", "https://example.com:8080/"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                sources.public_url(url)

    def test_redirect_to_private_target_is_not_requested(self):
        session = MagicMock()
        session.__enter__.return_value = session
        session.get.return_value = response(302, location="http://127.0.0.1/secrets")
        with patch.object(sources.requests, "Session", return_value=session), patch.object(
            sources, "public_url", side_effect=["https://example.com/", ValueError("Non-public URL")]
        ), self.assertRaises(ValueError):
            sources.OfferSourceReader().download("https://example.com/")
        session.get.assert_called_once()

    def test_html_contact_page_poster_and_structured_address_are_read(self):
        reader = sources.OfferSourceReader()
        pages = {
            "https://example.com/offer": ("text/html", b'''<main>Student deal
                <a href="/contact">Contact</a><img src="/poster.png">
                <a href="/checkout">Claim</a><img src="/logo.png"></main>
                <script>privateJavascript()</script>'''),
            "https://example.com/contact": ("text/html", b'''<p>Visit us</p><script type="application/ld+json">
                {"@type":"LocalBusiness","address":{"@type":"PostalAddress","streetAddress":"123 King St", "addressLocality":"Waterloo"}}
                </script><a href="/contact/deeper">Contact another page</a>'''),
            "https://example.com/poster.png": ("application/octet-stream", b"\x89PNG\r\n\x1a\nposter"),
        }
        reader.download = Mock(side_effect=lambda url, *_: (url, *pages[url]))
        evidence = reader.collect({"links": ["https://example.com/offer"]})
        self.assertTrue(evidence["complete"])
        self.assertEqual(reader.download.call_count, 3)
        self.assertIn("123 King St, Waterloo", evidence["sources"][1]["text"])
        self.assertNotIn("privateJavascript", evidence["sources"][0]["text"])
        self.assertEqual(evidence["media"][0]["mime_type"], "image/png")

    def test_login_response_and_unsupported_files_are_reported_as_errors(self):
        for final, mime, data in [
            ("https://member.wusa.ca/users/sign_in", "text/html", b"<h1>Sign in</h1>"),
            ("https://example.com/", "text/html", b'<a href="/users/auth/saml">Login</a>'),
            ("https://example.com/", "application/zip", b"not a poster"),
        ]:
            with self.subTest(mime=mime, final=final):
                reader = sources.OfferSourceReader()
                reader.download = Mock(return_value=(final, mime, data))
                evidence = reader.collect({"links": ["https://example.com/poster"]})
                self.assertFalse(evidence["complete"])
                self.assertEqual(evidence["sources"][0]["status"], "error")
                self.assertEqual(evidence["media"], [])

    def test_oversized_download_is_stopped(self):
        session = MagicMock()
        session.__enter__.return_value = session
        session.get.return_value = response(data=b"too much data")
        with patch.object(sources.requests, "Session", return_value=session), patch.object(sources, "public_url", side_effect=lambda url: url):
            with self.assertRaisesRegex(ValueError, "size limit"):
                sources.OfferSourceReader().download("https://example.com/poster", byte_limit=4)

    def test_source_limit_is_visible_and_not_marked_complete(self):
        reader = sources.OfferSourceReader()
        reader.download = Mock(side_effect=lambda url, *_: (url, "text/plain", b"hello"))
        evidence = reader.collect({"links": [f"https://example.com/{i}" for i in range(sources.MAX_SOURCES + 1)]})
        self.assertFalse(evidence["complete"])
        self.assertEqual(reader.download.call_count, sources.MAX_SOURCES)
        self.assertEqual(evidence["sources"][-1]["error"], "SourceLimit")

    def test_scraped_inline_posters_are_preserved_as_links(self):
        offers = scraper.parse_api_offers({"success": True, "offers": [{
            "title": "Coffee", "description": '<img src="/poster.png"><a href="https://example.com">Website</a>',
        }]})
        self.assertEqual(offers[0]["links"], ["https://example.com", "https://member.wusa.ca/poster.png"])


if __name__ == "__main__":
    unittest.main()
