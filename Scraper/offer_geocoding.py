"""Cached, sequential Nominatim lookups for public business locations in offers."""

import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlsplit

import requests

from offer_classification import addresses_from_locations, write_json

DEFAULT_URL = "https://nominatim.openstreetmap.org/search"
ATTRIBUTION = "© OpenStreetMap contributors, ODbL 1.0; geocoding by Nominatim"
INTERVAL_SECONDS = 15.1  # At most four requests/minute, including recurring jobs.


def location_queries(offer, region="Waterloo, Ontario, Canada"):
    result = offer.get("classification") or {}
    if result.get("category") not in {"IN_PERSON", "BOTH"} or result.get("status") == "error":
        return []
    locations = result.get("locations", [])
    addresses = result.get("addresses", addresses_from_locations(locations))
    # Explicit street addresses take priority over less specific names of the same branches.
    inputs = addresses or locations
    queries = []
    for location in dict.fromkeys(inputs):
        campus = bool(re.search(r"\bSLC\b|Student Life Centre", location, re.I))
        if campus:
            query = "Student Life Centre, Waterloo, Ontario, Canada"
        elif addresses:
            query = location
        else:
            query = re.sub(r"\([^)]*\)", "", location).strip(" ,")
            query = re.sub(r"\s+,", ",", query)
            region_city = region.split(",", 1)[0].strip()
            if region and not re.search(r"\b" + re.escape(region_city) + r"\b", query, re.I):
                query += ", " + region
        queries.append({"address": location, "query": query, "precision": "building" if campus else "place"})
    return queries


def candidate(value):
    if not isinstance(value, dict):
        raise ValueError("Invalid Nominatim candidate")
    lat, lon = float(value["lat"]), float(value["lon"])
    if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError("Invalid coordinates")
    return {"lat": lat, "lon": lon, "display_name": value.get("display_name", ""),
            "osm_type": value.get("osm_type"), "osm_id": value.get("osm_id"),
            "address_details": value.get("address", {}), "place_rank": int(value.get("place_rank", 0))}


def street_name(value):
    value = re.sub(r"^\s*\d+[A-Za-z]?\s+", "", value.split(",", 1)[0]).casefold()
    replacements = {"st": "street", "rd": "road", "ave": "avenue", "dr": "drive", "blvd": "boulevard",
                    "ln": "lane", "ct": "court", "cres": "crescent", "n": "north", "s": "south", "e": "east", "w": "west"}
    words = re.findall(r"[a-z0-9]+", value)
    return " ".join(replacements.get(word, word) for word in words)


def select_result(values, input_address):
    if not isinstance(values, list):
        raise ValueError("Unexpected Nominatim response")
    matches = []
    house_number = re.match(r"^\s*(\d+[A-Za-z]?)\b", input_address)
    for value in values:
        item = candidate(value)
        # Cities, whole streets, and regions are too broad for an offer marker.
        if item["place_rank"] < 28:
            continue
        if "student life centre" in input_address.casefold() and "student life centre" not in item["display_name"].casefold():
            continue
        if house_number:
            found_number = str(item["address_details"].get("house_number", ""))
            if found_number.casefold() != house_number[1].casefold():
                continue
            if street_name(input_address) != street_name(item["address_details"].get("road", "")):
                continue
        if not any((item["osm_type"], item["osm_id"], item["lat"], item["lon"]) ==
                   (old["osm_type"], old["osm_id"], old["lat"], old["lon"]) for old in matches):
            matches.append(item)
    if len(matches) == 1:
        return {"status": "matched", **matches[0]}
    if matches:
        return {"status": "ambiguous", "candidates": matches}
    return {"status": "not_found"}


def resolve_for_offer(result, offer, input_address):
    """Distinguish businesses at one street address using the offer's business name."""
    if result.get("status") != "ambiguous":
        return result
    matches = result.get("candidates", [])

    def name(value):
        return "".join(re.findall(r"\w+", value.casefold()))

    business_fields = ("shop", "amenity", "office", "tourism", "craft", "leisure")
    named = [item for item in matches if any(
        name(str(item.get("address_details", {}).get(field, ""))) == name(offer["title"])
        for field in business_fields
    )]
    if len(named) == 1:
        return {**result, **named[0], "status": "matched", "match_method": "business_name"}
    if named:
        return result
    # A numbered address can identify a building/plaza even when its shops differ.
    parts = input_address.split(",")
    number = re.match(r"^\s*(\d+[A-Za-z]?)\b", input_address)
    buildings = []
    if number and len(parts) > 1:
        for item in matches:
            address = item.get("address_details", {})
            city = address.get("city") or address.get("town") or address.get("village") or ""
            if (str(address.get("house_number", "")).casefold() == number[1].casefold()
                    and street_name(address.get("road", "")) == street_name(input_address)
                    and name(city) == name(parts[1].strip())
                    and not any(address.get(field) for field in business_fields)
                    and re.match(r"^" + re.escape(number[1]) + r"\b", item.get("display_name", ""), re.I)):
                buildings.append(item)
    if len(buildings) == 1:
        return {**result, **buildings[0], "status": "matched", "match_method": "street_address", "precision": "address"}
    return result


class NominatimGeocoder:
    def __init__(self, cache_path, *, url=None, user_agent=None, countrycodes="ca"):
        self.cache_path = Path(cache_path)
        self.url = url or os.environ.get("NOMINATIM_URL") or DEFAULT_URL
        if urlsplit(self.url).scheme not in {"http", "https"} or not urlsplit(self.url).hostname:
            raise ValueError("NOMINATIM_URL must be an HTTP(S) search endpoint")
        self.user_agent = user_agent or os.environ.get("NOMINATIM_USER_AGENT") or "WusaMembershipScraper/1.0 (WUSA business offer map)"
        self.countrycodes = countrycodes
        self.last_request = None
        self.unavailable = False
        self.cache = {"version": 1, "entries": {}}
        if self.cache_path.exists():
            try:
                value = json.loads(self.cache_path.read_text(encoding="utf-8"))
                if not isinstance(value, dict) or value.get("version") != 1 or not isinstance(value.get("entries"), dict):
                    raise ValueError("Invalid geocoding cache")
                self.cache = value
            except (ValueError, UnicodeError):
                print("Warning: rebuilding invalid geocoding cache.", file=sys.stderr)

    def lookup(self, query, input_address):
        key_data = {"version": 1, "url": self.url, "query": query.casefold(),
                    "input_address": input_address.casefold(), "countrycodes": self.countrycodes}
        key = hashlib.sha256(json.dumps(key_data, sort_keys=True).encode("utf-8")).hexdigest()
        if key in self.cache["entries"]:
            value = self.cache["entries"][key]
            if isinstance(value, dict) and value.get("status") in {"matched", "not_found", "ambiguous"}:
                return {**value, "cached": True}
        if self.unavailable:
            return {"status": "error", "error": "ServiceUnavailable", "cached": False}
        if self.last_request is not None:
            time.sleep(max(0, INTERVAL_SECONDS - (time.monotonic() - self.last_request)))
        print(f"Geocoding: {query}", file=sys.stderr)
        self.last_request = time.monotonic()
        try:
            # Separate session: never reuse WUSA cookies, headers, or API credentials.
            with requests.Session() as session:
                session.trust_env = False
                response = session.get(self.url, params={
                    "q": query, "format": "jsonv2", "limit": 3,
                    "addressdetails": 1, "countrycodes": self.countrycodes,
                }, headers={"User-Agent": self.user_agent, "Accept-Language": "en"}, timeout=30)
                response.raise_for_status()
                result = select_result(response.json(), input_address)
        except (requests.RequestException, ValueError, KeyError, TypeError, OverflowError) as exc:
            code = getattr(getattr(exc, "response", None), "status_code", None)
            if code in {403, 429, 500, 502, 503, 504}:
                self.unavailable = True
            print(f"Warning: geocoding failed ({'HTTP ' + str(code) if code else type(exc).__name__}); no marker created.", file=sys.stderr)
            return {"status": "error", "error": f"HTTP_{code}" if code else type(exc).__name__, "cached": False}
        self.cache["entries"][key] = result
        write_json(self.cache_path, self.cache)
        return {**result, "cached": False}


def geocode_offers(offers, cache_path, *, geocoder=None, region="Waterloo, Ontario, Canada", countrycodes="ca"):
    geocoder = geocoder or NominatimGeocoder(cache_path, countrycodes=countrycodes)
    enriched = []
    for offer in offers:
        places = []
        for item in location_queries(offer, region):
            # All campus labels resolve to one building query and share one cached lookup.
            lookup_address = item["query"] if item["precision"] == "building" else item["address"]
            result = geocoder.lookup(item["query"], lookup_address)
            result = resolve_for_offer(result, offer, item["address"])
            places.append({**item, **result, "provider": "nominatim", "attribution": ATTRIBUTION})
        enriched.append({**offer, "geocoded_locations": places})
    return enriched
