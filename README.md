# WusaMembershipScraper

Print WUSA offer titles, details, and links using your existing session cookies.
The scraper runs without opening a browser or prompting for sign-in.

## Setup with curl.trillworks

1. Open https://member.wusa.ca/your_offers in your signed-in browser.
2. Open Developer Tools > Network and reload the page.
3. Right-click the `your_offers` document request and choose **Copy as cURL (bash)**.
4. Convert it to Python using https://curlconverter.com/
5. Save the generated Python as `request.py` beside `Scraperpy.py`.
6. Run:

```powershell
python -m pip install -r requirements.txt
python Scraperpy.py
```

The script reads the generated `headers` and `cookies` dictionaries as data. It
does not execute the generated Python. Both a `Cookie` header and a separate
`cookies` dictionary are supported. The scraper fetches the JSON API used by the
offers page: `https://member.wusa.ca/api/member_offers/your_offers`.
See `request.example.py` for the expected dictionary format.

## Copy cURL directly

You can also save the copied cURL command as `request.curl` beside the script
and run `python Scraperpy.py`, skipping conversion. Use the bash cURL format.
If both default files exist, `request.py` takes priority.

To choose a different file explicitly:

```powershell
python Scraperpy.py --request-file my_request.py
python Scraperpy.py --curl-file my_request.curl
```

`WUSA_COOKIE` is also supported and overrides the copied Cookie header when set.
If cookies expire, replace your copied request with a fresh authenticated one.
`request.py` and `request.curl` are ignored by Git because they contain session
cookies. Keep other files containing cookies out of Git too.

## Parsing

```powershell
python Scraperpy.py --html offers.html
python Scraperpy.py --html offers.html --selector ".your-offer-class"
```

Live scraping uses the JSON API, including featured offers, and removes
duplicates by offer ID. The HTML parser supports saved tables and offer cards;
`--selector` applies only to `--html`. A saved JavaScript page containing just an
empty app container has no offer data; use live scraping for that page.
