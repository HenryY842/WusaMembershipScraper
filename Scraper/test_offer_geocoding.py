import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch

import requests

import offer_classification as classification
import offer_geocoding as geo
import Scraperpy as scraper


def offer(locations=None, addresses=None, category="IN_PERSON"):
    value = {"title": "Water deal", "details": [], "links": [], "classification": {
        "category": category, "confidence": 1.0, "reason": "The poster specifies this location.",
        "locations": locations or [], "model": "test-model", "cached": False, "status": "ok",
    }}
    if addresses is not None:
        value["classification"]["addresses"] = addresses
    return value


def match(osm_id=1, house_number="35", road="University Avenue East", rank=30):
    return {"lat": "43.47", "lon": "-80.52", "place_rank": rank, "osm_type": "way", "osm_id": osm_id,
            "display_name": "35 University Avenue East, Waterloo, Ontario, Canada",
            "address": {"house_number": house_number, "road": road}}


class GeocodingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cache = self.root / "geo.json"

    def test_legacy_locations_upgrade_only_explicit_street_addresses(self):
        old = {key: value for key, value in offer([
            "Student Life Centre Basement", "341 Weber St. N., Waterloo", "35 University Ave E, Waterloo",
        ])["classification"].items() if key in classification.CLASSIFICATION_SCHEMA["required"]}
        result = classification.validate_classification(old)
        self.assertEqual(result["addresses"], ["341 Weber St. N., Waterloo", "35 University Ave E, Waterloo"])

    def test_place_context_and_building_precision_without_inventing_street_address(self):
        query = geo.location_queries(offer(["SLC, NEAR RING ROAD"]))[0]
        self.assertEqual(query["address"], "SLC, NEAR RING ROAD")
        self.assertEqual(query["precision"], "building")
        self.assertIn("Waterloo, Ontario, Canada", query["query"])
        self.assertEqual(geo.location_queries(offer(["Waterloo"], category="ONLINE")), [])

    def test_multiple_explicit_branches_are_separate_queries(self):
        addresses = ["35 University Ave E, Waterloo", "324 Highland Rd W, Kitchener"]
        queries = geo.location_queries(offer(["Crystal Clear Water Company"], addresses))
        self.assertEqual([q["query"] for q in queries], addresses)

    def test_matching_house_number_and_street_required(self):
        result = geo.select_result([match()], "35 University Ave E, Waterloo")
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["lat"], 43.47)
        self.assertEqual(geo.select_result([match(house_number="34")], "35 University Ave E, Waterloo")["status"], "not_found")
        self.assertEqual(geo.select_result([match(road="King Street")], "35 University Ave E, Waterloo")["status"], "not_found")

    def test_ambiguous_and_broad_results_have_no_marker_coordinates(self):
        for values, status in [([match(1), match(2)], "ambiguous"), ([match(rank=16)], "not_found"), ([], "not_found")]:
            result = geo.select_result(values, "35 University Ave E, Waterloo")
            self.assertEqual(result["status"], status)
            self.assertNotIn("lat", result)

    def test_campus_building_cannot_match_an_unrelated_nearby_business(self):
        result = geo.select_result([match()], "Student Life Centre, Waterloo, Ontario, Canada")
        self.assertEqual(result["status"], "not_found")

    def test_business_name_resolves_multiple_places_at_one_address(self):
        building = geo.candidate(match(1))
        other = {**geo.candidate(match(2)), "address_details": {**match()["address"], "shop": "Other shop"}}
        business = {**geo.candidate(match(3)), "address_details": {**match()["address"], "shop": "Water deal"}}
        unresolved = {"status": "ambiguous", "candidates": [building, other, business], "cached": True}
        selected = geo.resolve_for_offer(unresolved, offer(), "35 University Ave E, Waterloo")
        self.assertEqual(selected["status"], "matched")
        self.assertEqual(selected["osm_id"], 3)
        self.assertEqual(selected["match_method"], "business_name")
        self.assertTrue(selected["cached"])
        self.assertEqual(unresolved["status"], "ambiguous")

    def test_exact_numbered_building_resolves_shops_but_is_labelled_address_precision(self):
        building = {**geo.candidate(match(1)), "address_details": {**match()["address"], "city": "Waterloo"}}
        shop = {**geo.candidate(match(2)), "address_details": {**match()["address"], "city": "Waterloo", "shop": "Other shop"}}
        unresolved = {"status": "ambiguous", "candidates": [building, shop]}
        selected = geo.resolve_for_offer(unresolved, offer(), "35 University Ave E, Waterloo")
        self.assertEqual(selected["osm_id"], 1)
        self.assertEqual(selected["precision"], "address")
        self.assertEqual(geo.resolve_for_offer(unresolved, offer(), "35 University Ave E, Kitchener")["status"], "ambiguous")

    def test_multiple_matching_businesses_still_require_review(self):
        businesses = [{**geo.candidate(match(i)), "address_details": {**match()["address"], "shop": "Water deal"}} for i in (1, 2)]
        selected = geo.resolve_for_offer({"status": "ambiguous", "candidates": businesses}, offer(), "35 University Ave E, Waterloo")
        self.assertEqual(selected["status"], "ambiguous")
        self.assertNotIn("lat", selected)

    def test_invalid_coordinates_are_rejected(self):
        for lat, lon in [("nan", "-80"), ("43", "181"), ("91", "-80")]:
            with self.subTest(lat=lat, lon=lon), self.assertRaises(ValueError):
                geo.select_result([{**match(), "lat": lat, "lon": lon}], "35 University Ave E")

    def test_identification_rate_limit_cache_and_no_wusa_credentials(self):
        response = Mock()
        response.json.return_value = [match()]
        session = MagicMock()
        session.__enter__.return_value = session
        session.get.return_value = response
        geocoder = geo.NominatimGeocoder(self.cache)
        with patch.object(geo.requests, "Session", return_value=session), patch.object(geo.time, "monotonic", return_value=100), patch.object(geo.time, "sleep") as sleep, contextlib.redirect_stderr(io.StringIO()):
            geocoder.lookup("First query", "35 University Ave E")
            geocoder.lookup("Second query", "35 University Ave E")
            cached = geocoder.lookup("First query", "35 University Ave E")
        self.assertEqual(session.get.call_count, 2)
        sleep.assert_called_once_with(geo.INTERVAL_SECONDS)
        headers = session.get.call_args.kwargs["headers"]
        self.assertIn("WusaMembershipScraper", headers["User-Agent"])
        self.assertNotIn("Cookie", headers)
        self.assertNotIn("Authorization", headers)
        self.assertFalse(session.trust_env)
        self.assertTrue(cached["cached"])
        with patch.object(geo.requests, "Session", side_effect=AssertionError("No network on cache hit")):
            self.assertTrue(geo.NominatimGeocoder(self.cache).lookup("First query", "35 University Ave E")["cached"])

    def test_no_match_is_cached_and_http_429_is_not_retried(self):
        response = Mock()
        response.json.return_value = []
        session = MagicMock()
        session.__enter__.return_value = session
        session.get.return_value = response
        geocoder = geo.NominatimGeocoder(self.cache)
        with patch.object(geo.requests, "Session", return_value=session), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(geocoder.lookup("Nowhere", "Nowhere")["status"], "not_found")
            self.assertTrue(geocoder.lookup("Nowhere", "Nowhere")["cached"])
        error_response = Mock(status_code=429)
        session.get.side_effect = requests.HTTPError("private details", response=error_response)
        with patch.object(geo.requests, "Session", return_value=session), patch.object(geo.time, "sleep"), contextlib.redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(geocoder.lookup("Other", "Other")["status"], "error")
            self.assertEqual(geocoder.lookup("Another", "Another")["status"], "error")
        self.assertEqual(session.get.call_count, 2)
        self.assertNotIn("private details", errors.getvalue())

    def test_geocoding_does_not_mutate_offers_or_replace_extracted_address(self):
        original = offer(addresses=["35 University Ave E, Waterloo"])
        before = copy.deepcopy(original)
        geocoder = Mock()
        geocoder.lookup.return_value = {"status": "matched", **geo.candidate(match())}
        enriched = geo.geocode_offers([original], self.cache, geocoder=geocoder)
        self.assertEqual(original, before)
        self.assertEqual(enriched[0]["geocoded_locations"][0]["address"], "35 University Ave E, Waterloo")
        self.assertIn("attribution", enriched[0]["geocoded_locations"][0])

    def test_saved_json_can_be_geocoded_without_scraping_or_gemini(self):
        saved = self.root / "offers.json"
        value = offer(addresses=["35 University Ave E, Waterloo"])
        classification.export_offers([value], saved)
        output = geo.geocode_offers([value], self.cache, geocoder=Mock(lookup=Mock(return_value={"status": "not_found"})))
        args = ["Scraperpy.py", "--offers-file", str(saved), "--geocode", "--geocode-cache", str(self.cache)]
        with patch.object(sys, "argv", args), patch.object(geo, "geocode_offers", return_value=output) as geocode, patch.object(scraper, "get_offers", side_effect=AssertionError("No scraping")), patch.object(classification, "create_client", side_effect=AssertionError("No Gemini")), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(scraper.main(), 0)
        self.assertEqual(json.loads(saved.read_text(encoding="utf-8"))["offers"][0]["geocoded_locations"][0]["status"], "not_found")
        geocode.assert_called_once()

    def test_classification_geocodes_by_default_and_can_explicitly_skip(self):
        saved = self.root / "offers.json"
        value = offer(addresses=["35 University Ave E, Waterloo"])
        classification.export_offers([value], saved)
        places = [{"status": "matched", "lat": 43.47, "lon": -80.52, "display_name": "Business address"}]
        output = [{**value, "geocoded_locations": places}]
        args = ["Scraperpy.py", "--offers-file", str(saved), "--classify"]
        with patch.object(classification, "classify_offers", return_value=[value]), patch.object(geo, "geocode_offers", return_value=output) as geocode, contextlib.redirect_stdout(io.StringIO()):
            with patch.object(sys, "argv", args):
                self.assertEqual(scraper.main(), 0)
            geocode.assert_called_once()
            self.assertEqual(json.loads(saved.read_text(encoding="utf-8"))["offers"][0]["geocoded_locations"], places)
            geocode.reset_mock()
            with patch.object(sys, "argv", args + ["--no-geocode"]):
                self.assertEqual(scraper.main(), 0)
            geocode.assert_not_called()


if __name__ == "__main__":
    unittest.main()
