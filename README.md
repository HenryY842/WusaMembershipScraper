# WUSA Rewards Map

A GitHub-friendly demo of a WUSA rewards map and its Python data pipeline. The
site loads synthetic sample data by default. Users can import a local JSON
export when they have authorized access to real offer data.

## Try the demo

Install Python, then run this from the repository root:

    python -m http.server 8000

Open http://localhost:8000/docs/ in a browser. The map starts with the sample
offers in docs/demo-rewards.json.

To view your own locally generated export, select **Import JSON** and choose
scraper/offers.json. The browser reads the selected file locally; it is not
uploaded. **Demo data** returns to the bundled example.

The site is static and can also be hosted with GitHub Pages. Choose the main
branch and docs folder as the publishing source in repository settings; see the
[GitHub Pages publishing instructions](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site).

## Configure the scraper

The public repository contains no WUSA cookies, Gemini key, or real offer
export. Configure access on your own computer only after you are authorized to
use the WUSA offers.

Install the Python packages:

    python -m pip install -r scraper/requirements.txt

Copy the environment template and edit the private copy:

    if (-not (Test-Path .env)) { Copy-Item .env.example .env }
    notepad .env

Set WUSA_COOKIE to your authenticated WUSA cookie string. Alternatively, save
the browser's authenticated offers request as scraper/request.curl:

1. Sign in to https://member.wusa.ca/your_offers.
2. Open Developer Tools, select **Network**, and reload the offers page.
3. Right-click its authenticated request and choose **Copy as cURL (bash)**.
4. Open scraper/request.curl in a text editor, paste the command, and save.

The scraper reads that request file as data; it does not execute it. Keep .env
and scraper/request.curl private. Both are ignored by Git. WUSA sessions expire,
so refresh the cookie or request file if access is rejected.

For Gemini classification, set GEMINI_API_KEY in .env. On Windows, the
encrypted-key setup can be used instead:

    .\scraper\setup-gemini-key.ps1

That setup prompts for the key and stores it encrypted for your Windows account.
If PowerShell blocks local scripts, allow them for the current PowerShell
process only:

    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

## Run the Python pipeline

From the repository root:

    python -m scraper.wusa_scraper

This fetches and prints the current offers. To classify offers, inspect linked
pages and posters, geocode found locations, and create a local JSON export:

    python -m scraper.wusa_scraper --classify --output scraper/offers.json

The pipeline works in four steps:

1. wusa_scraper fetches and parses WUSA offers using your local session.
2. gemini_classifier uses offer text and readable linked evidence to classify
   offers as IN_PERSON, ONLINE, BOTH, or UNKNOWN, and extract stated locations.
3. location_finder looks up those places with Nominatim.
4. The JSON export stores classifications and map coordinates locally.

The website does not read scraper/offers.json automatically. Import it from the
page so real offers stay local and the GitHub demo always opens with sample data.
Some pages may require JavaScript or a login and cannot be read. Gemini receives
the offer text and readable linked page or poster contents. Cookies are sent
only to WUSA, not to Gemini.

Useful options:

    # Re-read linked pages and posters even when the offer text has not changed
    python -m scraper.wusa_scraper --classify --refresh-links --output scraper/offers.json

    # Classify only the offer text from WUSA
    python -m scraper.wusa_scraper --classify --no-follow-links --output scraper/offers.json

    # Geocode an existing JSON export without scraping or Gemini
    python -m scraper.wusa_scraper --offers-file scraper/offers.json --geocode

Geocoding uses the public Nominatim service, caches results, and limits new
lookups to four per minute. Follow the
[Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/).
Do not use it for personal or confidential addresses.

## Optional monthly task on Windows

The monthly task runs as your Windows account at 9:00 a.m. on the first day of
each month. Save your Gemini key with the encrypted setup above, configure
WUSA_COOKIE or scraper/request.curl, then register the task:

    .\scraper\install-monthly-task.ps1

It runs the same classification and geocoding pipeline and saves logs in
scraper/logs/. If scraping or classification fails, the previous local export
is left unchanged. WUSA cookies may need periodic manual renewal.

## Project layout

- docs/ — static map, styles, script, icons, and synthetic demo data.
- scraper/wusa_scraper.py — command-line scraper and pipeline entry point.
- scraper/gemini_classifier.py — Gemini classification and JSON export.
- scraper/location_finder.py — Nominatim geocoding.
- scraper/offer_source_reader.py — linked webpage and poster reader.
- scraper/requirements.txt — Python dependencies.
- scraper/tests/ — offline tests.
- .env.example — safe configuration template; copy to .env for local values.

## Development

Run the offline tests from the repository root:

    python -m unittest discover -s scraper/tests -p "test_*.py"
