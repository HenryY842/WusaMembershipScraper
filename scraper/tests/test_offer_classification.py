import contextlib
import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scraper import gemini_classifier as classification
from scraper import wusa_scraper as scraper


def result(category="IN_PERSON"):
    return {"category": category, "confidence": 0.9, "reason": "Redeem at the counter.", "locations": ["Student Life Centre"], "addresses": []}


def fake_client(value=None):
    generate = Mock(return_value=SimpleNamespace(text=json.dumps(value or result())))
    return SimpleNamespace(models=SimpleNamespace(generate_content=generate))


class ClassificationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.cache = self.root / "cache.json"
        self.offers = [{"title": "Coffee", "details": ["Redeem at the Student Life Centre counter."], "links": ["https://member.wusa.ca/reward?token=secret#code"]}]
        reader_patch = patch("scraper.offer_source_reader.OfferSourceReader.collect", return_value={"sources": [], "media": [], "complete": True})
        self.read_sources = reader_patch.start()
        self.addCleanup(reader_patch.stop)
        geocode_patch = patch("scraper.location_finder.geocode_offers", side_effect=lambda offers, *args, **kwargs: [{**offer, "geocoded_locations": []} for offer in offers])
        self.geocode = geocode_patch.start()
        self.addCleanup(geocode_patch.stop)

    def classify(self, offers=None, client=None, model="test-model"):
        return classification.classify_offers(self.offers if offers is None else offers, self.cache, model, client or fake_client())

    def test_schema_and_input_keep_original_offers_unchanged(self):
        client = fake_client()
        original = copy.deepcopy(self.offers)
        enriched = self.classify(client=client)
        self.assertEqual(self.offers, original)
        self.assertEqual(enriched[0]["classification"]["category"], "IN_PERSON")
        call = client.models.generate_content.call_args.kwargs
        self.assertEqual(call["config"]["response_mime_type"], "application/json")
        self.assertEqual(call["config"]["response_json_schema"], classification.CLASSIFICATION_SCHEMA)
        self.assertNotIn("secret", call["contents"])
        self.assertNotIn("#code", call["contents"])
        self.assertEqual(enriched[0]["links"], original[0]["links"])

    def test_all_four_categories_are_valid(self):
        for category in classification.CATEGORIES:
            self.assertEqual(classification.validate_classification(result(category))["category"], category)

    def test_invalid_fields_and_confidence_are_rejected(self):
        for value in [
            {**result(), "category": "PHYSICAL"}, {**result(), "confidence": True},
            {**result(), "confidence": float("nan")}, {**result(), "confidence": 1.1},
            {**result(), "locations": [None]}, {**result(), "reason": ""},
            {**result(), "extra": "field"}, {"category": "ONLINE"},
        ]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                classification.validate_classification(value)

    def test_unchanged_offers_use_cache_without_api_key_or_sdk(self):
        self.classify()
        with patch.dict(os.environ, {}, clear=True), patch.object(classification, "create_client", side_effect=AssertionError("Cache hit must not create a client")):
            enriched = classification.classify_offers(self.offers, self.cache, "test-model")
        self.assertTrue(enriched[0]["classification"]["cached"])

    def test_changed_offer_and_model_and_prompt_invalidate_cache(self):
        self.classify()
        changed = copy.deepcopy(self.offers)
        changed[0]["details"].append("Also available online.")
        client = fake_client(result("BOTH"))
        self.classify(offers=changed, client=client)
        self.classify(client=client, model="another-model")
        with patch.object(classification, "PROMPT_VERSION", classification.PROMPT_VERSION + 1):
            self.classify(client=client)
        self.assertEqual(client.models.generate_content.call_count, 3)

    def test_duplicate_offers_only_make_one_request(self):
        client = fake_client()
        enriched = self.classify(offers=self.offers * 2, client=client)
        self.assertEqual(client.models.generate_content.call_count, 1)
        self.assertTrue(enriched[1]["classification"]["cached"])

    def test_completed_run_replaces_obsolete_cache_and_records_offer_names(self):
        self.classify(client=fake_client(result("UNKNOWN")))
        changed = copy.deepcopy(self.offers)
        changed[0]["details"].append("Updated poster: visit the counter.")
        self.classify(offers=changed)
        cache = json.loads(self.cache.read_text(encoding="utf-8"))
        current_key = classification.cache_key(changed[0], "test-model")
        self.assertEqual(set(cache["entries"]), {current_key})
        self.assertEqual(cache["entries"][current_key]["category"], "IN_PERSON")
        self.assertEqual(cache["offer_titles"], {current_key: "Coffee"})
        self.assertEqual(set(cache["sources"]), {current_key})

    def test_cache_sync_excludes_partial_and_failed_classifications(self):
        enriched = self.classify()
        partial = {**enriched[0], "title": "Partial", "classification": {**enriched[0]["classification"], "status": "partial"}}
        failed = {**enriched[0], "title": "Failed", "classification": {**enriched[0]["classification"], "status": "error"}}
        classification.save_current_cache(enriched + [partial, failed], self.cache, "test-model")
        cache = json.loads(self.cache.read_text(encoding="utf-8"))
        self.assertEqual(len(cache["entries"]), 1)
        self.assertEqual(list(cache["offer_titles"].values()), ["Coffee"])

    def test_real_unknown_classifications_are_cached(self):
        self.classify(client=fake_client(result("UNKNOWN")))
        client = fake_client()
        self.assertTrue(self.classify(client=client)[0]["classification"]["cached"])
        client.models.generate_content.assert_not_called()

    def test_linked_text_and_poster_are_sent_to_gemini_and_sources_exported(self):
        self.read_sources.return_value = {
            "sources": [{"url": "https://example.com/poster.pdf", "status": "ok", "content_type": "application/pdf"},
                        {"url": "https://example.com/contact", "status": "ok", "text": "Visit 123 King St, Waterloo."}],
            "media": [{"url": "https://example.com/poster.pdf", "mime_type": "application/pdf", "data": b"%PDF-test"}],
            "complete": True,
        }
        client = fake_client({**result(), "locations": ["123 King St, Waterloo"]})
        enriched = self.classify(client=client)
        parts = client.models.generate_content.call_args.kwargs["contents"]
        self.assertIn("123 King St", parts[0].text)
        self.assertEqual(parts[2].inline_data.data, b"%PDF-test")
        self.assertEqual(parts[2].inline_data.mime_type, "application/pdf")
        self.assertEqual(enriched[0]["classification"]["locations"], ["123 King St, Waterloo"])
        self.assertNotIn("text", enriched[0]["classification"]["sources"][1])
        self.assertNotIn("123 King St, Waterloo.", self.cache.read_text())
        self.read_sources.reset_mock()
        cached = self.classify(client=client)
        self.read_sources.assert_not_called()
        self.assertEqual(cached[0]["classification"]["sources"], enriched[0]["classification"]["sources"])

    def test_failed_link_is_partial_and_retried_instead_of_cached(self):
        self.read_sources.return_value = {
            "sources": [{"url": "https://example.com/poster.pdf", "status": "error", "error": "HTTPError"}],
            "media": [], "complete": False,
        }
        client = fake_client()
        with contextlib.redirect_stderr(io.StringIO()):
            enriched = self.classify(client=client)
            self.classify(client=client)
        self.assertEqual(enriched[0]["classification"]["status"], "partial")
        self.assertFalse(self.cache.exists())
        self.assertEqual(client.models.generate_content.call_count, 2)

    def test_refresh_reloads_evidence_and_no_follow_uses_separate_cache(self):
        self.classify()
        client = fake_client()
        classification.classify_offers(self.offers, self.cache, "test-model", client, refresh_links=True)
        self.assertEqual(self.read_sources.call_count, 2)
        self.read_sources.reset_mock()
        classification.classify_offers(self.offers, self.cache, "test-model", client, follow_links=False)
        self.read_sources.assert_not_called()
        self.assertEqual(client.models.generate_content.call_count, 2)

    def test_api_outage_stops_link_downloads_as_well(self):
        class QuotaError(Exception):
            code = 429
        client = fake_client()
        client.models.generate_content.side_effect = QuotaError()
        with contextlib.redirect_stderr(io.StringIO()):
            self.classify(offers=self.offers + [{**self.offers[0], "title": "Other"}], client=client)
        self.read_sources.assert_called_once()

    def test_failed_refresh_does_not_reuse_stale_result_next_run(self):
        self.classify()
        self.read_sources.return_value = {
            "sources": [{"url": "https://example.com/poster", "status": "error"}],
            "media": [], "complete": False,
        }
        client = fake_client()
        with contextlib.redirect_stderr(io.StringIO()):
            classification.classify_offers(self.offers, self.cache, "test-model", client, refresh_links=True)
            retried = self.classify(client=client)
        self.assertEqual(client.models.generate_content.call_count, 2)
        self.assertFalse(retried[0]["classification"]["cached"])

    def test_invalid_or_failed_responses_are_unknown_and_not_cached(self):
        client = fake_client()
        for response in ["not JSON", json.dumps({**result(), "category": "INVALID"})]:
            client.models.generate_content.return_value.text = response
            with contextlib.redirect_stderr(io.StringIO()):
                enriched = self.classify(client=client)
            self.assertEqual(enriched[0]["classification"]["category"], "UNKNOWN")
            self.assertEqual(enriched[0]["classification"]["status"], "error")
            self.assertFalse(self.cache.exists())
        self.assertEqual(self.classify()[0]["classification"]["status"], "ok")

    def test_quota_failure_stops_further_api_calls(self):
        class QuotaError(Exception):
            code = 429
        client = fake_client()
        client.models.generate_content.side_effect = QuotaError("private credentials")
        other = {**self.offers[0], "title": "Lunch"}
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            enriched = self.classify(offers=self.offers + [other], client=client)
        self.assertEqual(client.models.generate_content.call_count, 1)
        self.assertTrue(all(offer["classification"]["status"] == "error" for offer in enriched))
        self.assertNotIn("private credentials", errors.getvalue())

    def test_transient_server_failure_is_retried(self):
        class ServerError(Exception):
            code = 503
        client = fake_client()
        client.models.generate_content.side_effect = [ServerError("private credentials"), SimpleNamespace(text=json.dumps(result()))]
        errors = io.StringIO()
        with patch.object(classification.time, "sleep"), contextlib.redirect_stderr(errors):
            enriched = self.classify(client=client)
        self.assertEqual(client.models.generate_content.call_count, 2)
        self.assertEqual(enriched[0]["classification"]["status"], "ok")
        self.assertIn("HTTP 503", errors.getvalue())
        self.assertNotIn("private credentials", errors.getvalue())

    def test_exhausted_server_retries_do_not_skip_other_offers(self):
        class ServerError(Exception):
            code = 500
        client = fake_client()
        client.models.generate_content.side_effect = [ServerError()] * 3 + [SimpleNamespace(text=json.dumps(result()))]
        other = {**self.offers[0], "title": "Lunch"}
        with patch.object(classification.time, "sleep"), contextlib.redirect_stderr(io.StringIO()):
            enriched = self.classify(offers=self.offers + [other], client=client)
        self.assertEqual(client.models.generate_content.call_count, 4)
        self.assertEqual(enriched[0]["classification"]["status"], "error")
        self.assertEqual(enriched[1]["classification"]["status"], "ok")

    def test_corrupt_cache_and_bad_cache_entry_are_rebuilt(self):
        self.cache.write_text("broken", encoding="utf-8")
        with contextlib.redirect_stderr(io.StringIO()):
            self.classify()
        data = json.loads(self.cache.read_text())
        key = classification.cache_key(self.offers[0], "test-model")
        data["entries"][key] = {"category": "bad"}
        classification.write_json(self.cache, data)
        client = fake_client()
        self.classify(client=client)
        client.models.generate_content.assert_called_once()

    def test_missing_key_is_actionable_and_empty_offers_need_no_key(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(ValueError, "GEMINI_API_KEY"):
            classification.classify_offers(self.offers, self.cache)
        self.assertEqual(classification.classify_offers([], self.cache), [])

    def test_json_export_preserves_data_and_null_for_unclassified(self):
        output = self.root / "data" / "offers.json"
        classification.export_offers(self.offers, output)
        data = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["offers"][0], {**self.offers[0], "classification": None})
        classification.export_offers(self.classify(), output)
        self.assertEqual(json.loads(output.read_text())["offers"][0]["classification"]["category"], "IN_PERSON")

    def test_plain_cli_does_not_classify_and_keeps_original_output(self):
        html = self.root / "offers.html"
        html.write_text("<main><article><h3>Coffee</h3><p>20% off</p></article></main>", encoding="utf-8")
        expected = io.StringIO()
        with contextlib.redirect_stdout(expected):
            scraper.print_offers(scraper.parse_offers(html.read_text()))
        output = io.StringIO()
        with patch.object(sys, "argv", ["wusa_scraper.py", "--html", str(html)]), patch.object(classification, "classify_offers", side_effect=AssertionError("Should not classify")), patch.dict(sys.modules, {"google.genai": None}), contextlib.redirect_stdout(output):
            self.assertEqual(scraper.main(), 0)
        self.assertEqual(output.getvalue(), expected.getvalue())

    def test_classified_cli_exports_and_uses_selected_model(self):
        html = self.root / "offers.html"
        html.write_text("<main><article><h3>Coffee</h3><p>20% off</p></article></main>", encoding="utf-8")
        output = self.root / "offers.json"
        client = fake_client()
        with patch.object(sys, "argv", ["wusa_scraper.py", "--html", str(html), "--classify", "--cache-file", str(self.cache), "--gemini-model", "test-model", "--output", str(output)]), patch.object(classification, "create_client", return_value=client), contextlib.redirect_stdout(io.StringIO()):
            client.close = Mock()
            self.assertEqual(scraper.main(), 0)
        self.assertEqual(json.loads(output.read_text())["offers"][0]["classification"]["category"], "IN_PERSON")
        self.assertEqual(client.models.generate_content.call_args.kwargs["model"], "test-model")
        client.close.assert_called_once()

    def test_classified_cli_automatically_keeps_export_and_cache_in_sync(self):
        html = self.root / "offers.html"
        html.write_text("<main><article><h3>Coffee</h3><p>Redeem at counter.</p></article></main>", encoding="utf-8")
        output = self.root / "offers.json"
        client = fake_client()
        client.close = Mock()
        args = ["wusa_scraper.py", "--html", str(html), "--classify", "--cache-file", str(self.cache), "--gemini-model", "test-model"]
        with patch.object(sys, "argv", args), patch.object(scraper, "PROJECT_DIR", self.root), patch.object(classification, "create_client", return_value=client), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(scraper.main(), 0)
            first = json.loads(output.read_text(encoding="utf-8"))["offers"][0]
            self.assertEqual(first["classification"]["category"], "IN_PERSON")
            # A changed offer must update both files without requiring --output.
            html.write_text("<main><article><h3>Coffee</h3><p>Redeem online.</p></article></main>", encoding="utf-8")
            client.models.generate_content.return_value.text = json.dumps(result("ONLINE"))
            self.assertEqual(scraper.main(), 0)
            updated = json.loads(output.read_text(encoding="utf-8"))["offers"][0]
            cache = json.loads(self.cache.read_text(encoding="utf-8"))
            key = classification.cache_key(updated, "test-model")
            self.assertEqual(updated["classification"]["category"], "ONLINE")
            self.assertEqual(set(cache["entries"]), {key})
            self.assertEqual(cache["entries"][key], {name: updated["classification"][name] for name in classification.CLASSIFICATION_SCHEMA["required"]})
            # Recreate a missing export from cached results without an API key.
            output.unlink()
            with patch.object(classification, "create_client", side_effect=AssertionError("Cache must supply classification")):
                self.assertEqual(scraper.main(), 0)
            self.assertTrue(output.exists())
            self.assertEqual(client.models.generate_content.call_count, 2)


if __name__ == "__main__":
    unittest.main()

