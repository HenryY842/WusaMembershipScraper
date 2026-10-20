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
python Scraper/Scraperpy.py --classify --output Website/offers.json
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
of explicitly stated place names or addresses). Locations are not geocoded and
coordinates are not generated. Only the scraped title/details and links without
query strings or fragments are sent for classification; browser cookies and
headers are not sent to Gemini. Links are not downloaded by the classifier.

Successful results are cached in `Scraper/.classification_cache.json`. Unchanged
offer content reuses cached results, including valid `UNKNOWN` classifications.
Changes to the content, selected model, or prompt version cause reclassification.
Use `--cache-file PATH` to choose another cache; delete it to start fresh.
Fully cached runs do not need an API key or Gemini SDK.

API failures or invalid responses produce `UNKNOWN` with `status: "error"` and
are not cached, so a later run retries them. A missing API key on a cache miss
produces a configuration error. Quota/authentication/server errors stop further
Gemini requests for that run; existing cached classifications are still reused.

## JSON export

Export is optional and also works without Gemini:

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

Without `--classify`, `classification` is `null`. The original title, details,
and links remain intact. From JavaScript, read `(await response.json()).offers`
and filter using `offer.classification?.category`. Only offers with independently
verified coordinates should become map markers.

Run the offline classification and CLI tests:

```powershell
python -m unittest discover -s Scraper -p "test_*.py"
```
