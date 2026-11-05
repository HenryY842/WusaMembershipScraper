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

import offer_classification as classification
import Scraperpy as scraper


def result(category="IN_PERSON"):
    return {"category": category, "confidence": 0.9, "reason": "Redeem at the counter.", "locations": ["Student Life Centre"]}


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
        with patch.object(classification, "PROMPT_VERSION", 2):
            self.classify(client=client)
        self.assertEqual(client.models.generate_content.call_count, 3)

    def test_duplicate_offers_only_make_one_request(self):
        client = fake_client()
        enriched = self.classify(offers=self.offers * 2, client=client)
        self.assertEqual(client.models.generate_content.call_count, 1)
        self.assertTrue(enriched[1]["classification"]["cached"])

    def test_real_unknown_classifications_are_cached(self):
        self.classify(client=fake_client(result("UNKNOWN")))
        client = fake_client()
        self.assertTrue(self.classify(client=client)[0]["classification"]["cached"])
        client.models.generate_content.assert_not_called()

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
        with patch.object(sys, "argv", ["Scraperpy.py", "--html", str(html)]), patch.object(classification, "classify_offers", side_effect=AssertionError("Should not classify")), patch.dict(sys.modules, {"google.genai": None}), contextlib.redirect_stdout(output):
            self.assertEqual(scraper.main(), 0)
        self.assertEqual(output.getvalue(), expected.getvalue())

    def test_classified_cli_exports_and_uses_selected_model(self):
        html = self.root / "offers.html"
        html.write_text("<main><article><h3>Coffee</h3><p>20% off</p></article></main>", encoding="utf-8")
        output = self.root / "offers.json"
        client = fake_client()
        with patch.object(sys, "argv", ["Scraperpy.py", "--html", str(html), "--classify", "--cache-file", str(self.cache), "--gemini-model", "test-model", "--output", str(output)]), patch.object(classification, "create_client", return_value=client), contextlib.redirect_stdout(io.StringIO()):
            client.close = Mock()
            self.assertEqual(scraper.main(), 0)
        self.assertEqual(json.loads(output.read_text())["offers"][0]["classification"]["category"], "IN_PERSON")
        self.assertEqual(client.models.generate_content.call_args.kwargs["model"], "test-model")
        client.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()

