# WusaMembershipScraper

Print offers from https://member.wusa.ca/your_offers, including details and links.
The site requires Waterloo sign-in.

## Run

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
python Scraperpy.py --login
```

Sign in in the browser window, including any MFA prompt. Once your offers are
visible, press Enter in the terminal. The script prints the offers and closes the
browser. It does not save your credentials or browser session.

Alternatively, set `WUSA_COOKIE` in your environment to the Cookie header from
your own authenticated WUSA session and run `python Scraperpy.py`. Treat this
value as a secret and do not commit it or paste it into chat.

To parse a saved offers page without network access:

```powershell
python Scraperpy.py --html offers.html
```

The parser supports HTML tables and offer cards. If the signed-in page uses a
different layout, pass the CSS selector matching each offer:

```powershell
python Scraperpy.py --login --selector ".your-offer-class"
```

The authenticated offers layout has not yet been verified against a live session.
