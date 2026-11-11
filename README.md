# WusaMembershipScraper

Print WUSA offer titles, details, and links using your existing session cookies.
The scraper runs without opening a browser or prompting for sign-in.

## Setup with curl.trillworks

1. Open https://member.wusa.ca/your_offers in your signed-in browser.
2. Open Developer Tools > Network and reload the page.
3. Right-click the `your_offers` document request and choose **Copy as cURL (bash)**.
4. Convert it to Python using https://curlconverter.com/
5. Save the generated Python as `Scraper/request.py` beside `Scraperpy.py`.
6. Run:

```powershell
python -m pip install -r requirements.txt
python Scraper/Scraperpy.py
```

The script reads the generated `headers` and `cookies` dictionaries as data. It
does not execute the generated Python. Both a `Cookie` header and a separate
`cookies` dictionary are supported. The scraper fetches the JSON API used by the
offers page: `https://member.wusa.ca/api/member_offers/your_offers`.
See `Scraper/request.example.py` for the expected dictionary format.

## Copy cURL directly

You can also save the copied cURL command as `request.curl` beside the script
and run `python Scraper/Scraperpy.py`, skipping conversion. Use the bash cURL format.
If both default files exist, `request.py` takes priority.

To choose a different file explicitly:

```powershell
python Scraper/Scraperpy.py --request-file my_request.py
python Scraper/Scraperpy.py --curl-file my_request.curl
```

`WUSA_COOKIE` is also supported and overrides the copied Cookie header when set.
If cookies expire, replace your copied request with a fresh authenticated one.
`request.py` and `request.curl` are ignored by Git because they contain session
cookies. Keep other files containing cookies out of Git too.

## Parsing

```powershell
python Scraper/Scraperpy.py --html offers.html
python Scraper/Scraperpy.py --html offers.html --selector ".your-offer-class"
```

Live scraping uses the JSON API, including featured offers, and removes
duplicates by offer ID. The HTML parser supports saved tables and offer cards;
`--selector` applies only to `--html`. A saved JavaScript page containing just an
empty app container has no offer data; use live scraping for that page.

## Optional Gemini classification

Plain runs keep the existing scraping and console output. Add `--classify` to
classify offers after scraping. Set your API key in the environment:

```powershell
python -m pip install -r requirements.txt
$env:GEMINI_API_KEY = "YOUR_API_KEY"
python Scraper/Scraperpy.py --classify
```

`GOOGLE_API_KEY` is also supported. The default model is `gemini-3.5-flash-lite`;
override it with `--gemini-model MODEL` or `GEMINI_MODEL`.
The implementation uses Google's [structured JSON output](https://googleapis.github.io/python-genai/#json-response-schema)
and validates the response locally.

Categories describe redemption, rather than where a coupon is claimed:

| Category | Meaning |
| --- | --- |
| `IN_PERSON` | Requires visiting a physical business or service location. |
| `ONLINE` | Redeemed through a website, app, digital subscription, or online order. |
| `BOTH` | Explicitly supports both online and in-person redemption. |
| `UNKNOWN` | The available offer data does not establish the method. |

Gemini returns `category`, `confidence` (0–1), `reason`, and `locations` (an array
of explicitly stated place names or addresses), plus `addresses` (street/postal
addresses only). Missing street addresses stay `[]`; building names remain in
`locations`. Older saved results can populate `addresses` from street addresses
already present in their location text. Gemini does not generate coordinates;
Nominatim looks them up by default during classification (use `--no-geocode`
to skip coordinate searches).

`--classify` also downloads each offer's linked webpages and posters. Webpage
text (including structured addresses), PDF files, and PNG/JPEG/WebP/HEIC/HEIF
images are sent to Gemini so it can read addresses printed on posters. The
reader also follows one level of contact/location pages on the same website and
embedded posters or linked documents. It uses HTTP downloads, so pages that
require JavaScript, CAPTCHAs, or another website's login may be unreadable.
It does not submit forms, redeem offers, or generate coordinates.

The saved WUSA session is used for WUSA poster downloads. Its cookies and
authorization headers are only sent to `https://member.wusa.ca`, including when
a download redirects to another host. Cookies and request headers are not sent
to Gemini. Source URLs sent to Gemini have query strings/fragments removed;
downloaded webpage text and poster contents are sent as evidence.

Each exported classification has a `sources` array listing the URLs, content
types, and whether reading succeeded. `status: "partial"` means Gemini returned
a classification but some sources were unreadable; it is not cached and will
be retried. A source's `error` identifies the failure type without exposing
credentials. Limits per offer are eight resources, 5 MiB per file, 12 MiB total,
18,000 characters per HTML page, and a 90-second download budget with connection
and read timeouts. Skipped resources are reported in the source list.

Every completed `--classify` run automatically updates both
`Scraper/.classification_cache.json` and `Scraper/offers.json` from the same
results, including runs that reuse cached classifications. No `--output` flag
is needed. This also recreates a missing `offers.json` from cached results.

```powershell
python Scraper/Scraperpy.py --classify
```

To read changed posters/websites again even when the WUSA text is unchanged:

```powershell
python Scraper/Scraperpy.py --classify --refresh-links
```

Use `--classify --no-follow-links` to classify only the original WUSA text.
This uses a separate cache key from classification with downloaded evidence.

Successful results are cached in `Scraper/.classification_cache.json`. Unchanged
offer content reuses cached results, including valid `UNKNOWN` classifications.
After a completed run, the cache keeps only successful results for that run's
offers, model, and link-reading mode. Obsolete entries are removed rather than
left beside the latest classifications. The `offer_titles` map identifies the
offer name belonging to each hashed key. Partial/error results remain uncached.
Changes to the WUSA content, selected model, prompt version, or link-reading mode
cause reclassification. This update invalidates older text-only classifications.
Cached results do not download sources again; use `--refresh-links` when external
content changes. Cache/export files store source metadata, not webpage text or
poster bytes. Use `--cache-file PATH` to choose another cache; delete it to start fresh.
Fully cached runs do not need an API key or Gemini SDK.

API failures or invalid responses produce `UNKNOWN` with `status: "error"` and
are not cached, so a later run retries them. A missing API key on a cache miss
produces a configuration error. Temporary server errors are retried twice; if an
offer still fails, the run continues with the next offer. Quota, authentication,
or configuration errors stop further Gemini requests for that run; existing
cached classifications are still reused. API warnings include HTTP status codes
without printing potentially sensitive exception bodies.

## JSON export

Classified runs export automatically to `Scraper/offers.json`. Use `--output`
to choose a different destination, such as `--classify --output Website/offers.json`;
the cache still updates during the same run. Files are saved before printing the
offer list. This synchronization happens when the script runs, rather than
watching for manual edits to JSON files.

Without `--classify`, export is optional and requires `--output`:

```powershell
python Scraper/Scraperpy.py --output Website/offers.json
```

The UTF-8 JSON file contains an `offers` array for your React/Leaflet application:

```json
{
  "schema_version": 1,
  "generated_at": "2026-10-20T12:00:00+00:00",
  "offers": [
    {
      "title": "Campus coffee",
      "details": ["Redeem at the Student Life Centre counter."],
      "links": ["https://example.com/offer"],
      "classification": {
        "category": "IN_PERSON",
        "confidence": 0.95,
        "reason": "The offer explicitly requires counter redemption.",
        "locations": ["Student Life Centre"],
        "model": "gemini-3.5-flash-lite",
        "cached": false,
        "status": "ok"
      }
    }
  ]
}
```

Without `--classify`, newly scraped offers have `classification: null`; reading
`--offers-file` preserves saved classifications. The original title, details,
and links remain intact. From JavaScript, read `(await response.json()).offers`
and filter using `offer.classification?.category`.

## Addresses, Nominatim, and map markers

Classify and automatically geocode found business addresses or place names:

```powershell
python Scraper/Scraperpy.py --classify
```

Geocoding is enabled automatically with `--classify`, so regular classification
runs keep map coordinates in the exported JSON. `--geocode` remains available
for saved offers without classification. Use `--classify --no-geocode` when you
intentionally want to skip Nominatim.

Geocode the existing JSON without scraping or using a Gemini API key:

```powershell
python Scraper/Scraperpy.py --offers-file Scraper/offers.json --geocode
```

The saved JSON now includes:

```json
{
  "classification": {
    "addresses": ["341 Weber St. N., Waterloo"]
  },
  "geocoded_locations": [
    {
      "address": "341 Weber St. N., Waterloo",
      "query": "341 Weber St. N., Waterloo",
      "status": "matched",
      "lat": 43.0,
      "lon": -80.0,
      "display_name": "Matched address returned by Nominatim",
      "precision": "place",
      "provider": "nominatim"
    }
  ]
}
```

The example coordinates above are placeholders. Actual coordinates come from
Nominatim. Online-only offers are not mapped. Each branch gets its own result.
Campus labels such as SLC Food Court resolve to the Student Life Centre building
and have `precision: "building"`; this does not identify a specific indoor
counter or floor. Queries prefer extracted street addresses. Otherwise, place
names use `--geocode-region` (default `Waterloo, Ontario, Canada`). Country results
are restricted by `--geocode-country` (default `ca`). Multiple plausible matches,
broad city/street results, unmatched street numbers/names, and failed requests
do not get marker coordinates. Inspect `ambiguous`, `not_found`, or `error`
statuses for unresolved locations rather than assuming every offer is mapped.
When several results share an address, an exact match between the business name
and the offer title can identify the right shop. Otherwise a single numbered
building matching the street and city can be mapped with `precision: "address"`;
this locates the supplied street address rather than confirming a storefront.
Unresolved candidate ties remain unplotted. This selection also works on cached
results without new Nominatim requests.

**Public Nominatim usage:** follow the
[Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/).
This is a small lookup task for public business locations in WUSA offers. The
script uses one thread, identifies the application, caches matches/no-matches
in `Scraper/.geocoding_cache.json`, and limits uncached lookups to four per minute
(15.1 seconds apart), including recurring runs. Run only one geocoding process
on one machine. It stops new lookups on throttling/service errors. Do not use
this as a generic address-search service or send personal/confidential addresses.
For larger workloads, use another provider or a self-hosted instance.

Set `NOMINATIM_URL` to switch to another compatible `/search` endpoint without
changing code. `NOMINATIM_USER_AGENT` can supply your application/contact details.
Use `--geocode-cache PATH` for a different result cache; delete the cache to retry
previous no-matches after correcting their addresses. Geocoding does not receive
your WUSA cookies or Gemini key. Its requests use the
[Nominatim search API](https://nominatim.org/release-docs/latest/api/Search/).

The gold-and-black Leaflet page reads `Scraper/offers.json`. The Online, In person,
and Both tabs filter the map and offer details together; In person is selected
initially. Tabs support arrow keys, Home, and End. Online offers show their links
without physical map pins. Each offer row includes its description, expiry when
provided, and addresses/poster/website links. The two-column layout stacks on
phones. No additional Nominatim requests are made by switching tabs.

The map plots only results with `status: "matched"`. Hover over a pin to see its label; click it to see the
address found by Nominatim and the offers there. Offers at the same coordinates
share a popup. The map opens around the offer pins and GPS updates do not move
it away from them. The "Show all offer pins" button restores their view.
Each pin shows the number of offers in the selected category sharing it. The
status counts mapped offers separately from map locations. The details below
the map include every offer in the selected category, its addresses, "View on map"
buttons, and any unresolved locations.
OpenStreetMap attribution remains visible. Serve the entire project root so the page can fetch
its sibling `Scraper` folder:

```powershell
python -m http.server 8000
```

Open `http://localhost:8000/Website/MembershipMapWebsite.html`. For a different
export location, change the map element's `data-offers-url` in the HTML. Loading
the map uses saved coordinates and makes no Nominatim lookup requests.

Run the offline classification and CLI tests:

```powershell
python -m unittest discover -s Scraper -p "test_*.py"
```
