# WUSA Rewards Map

A simple map for browsing student offers.

## Try the demo

**The sample website needs no WUSA cookies, Gemini key, or Python packages.**
It starts with made-up sample offers, so you can try it without signing in or
connecting to WUSA.

If you downloaded this project on Windows, double-click start-demo.bat in the
top-level project folder. It starts the server in the correct folder for you.
Leave the window open, then open http://localhost:8000/docs/ in your browser.
Press Ctrl+C in the server window when you are done.

Or, open PowerShell in the top-level project folder and run:

    python -m http.server 8000

Then open http://localhost:8000/docs/ in your browser and leave the PowerShell
window open while you use the page.

Do not double-click docs/index.html or use GitHub's code preview; those do not
run the demo page. Use the local address above or publish the docs folder with
GitHub Pages.

Choose **Online**, **In person**, or **All** to browse the sample. Choose
**Import JSON** to select an offers file on your computer. The file is read by
your browser and is not uploaded. Choose **Demo data** to return to the sample.

## Use your own WUSA offers (optional)

Only use this with an account and offers you are authorized to access. The demo
works without cookies. WUSA cookies act like a temporary sign-in, so keep them
private and never commit them or include them in a video or screenshot.

### Copy your signed-in request with cURL

These steps use Chrome. Other browsers have similar developer tools.

1. Sign in to WUSA in Chrome and open the offers page.
2. Press **F12** (or right-click the page and choose **Inspect**) and open the
   **Network** tab. Reload the offers page so the requests appear.
3. Find the request for the offers list. Select it and confirm its address is
   the WUSA offers API request. Right-click it and choose **Copy as cURL
   (bash)**. Do not share the copied command; it contains your session.
4. In the project folder, open or create `scraper/request.curl` in a text
   editor. Paste the entire copied cURL command as Chrome copied it and save
   the file. Keep any line breaks and backslashes.
   Do not run the command in a terminal and do not paste it into `.env.example`.
   The scraper reads the headers and cookies from this file as text, then makes
   its own offers request.
5. Install the Python packages if you have not already:

       python -m pip install -r scraper/requirements.txt

6. Run the scraper and save your offers locally:

       python -m scraper.wusa_scraper --classify --output scraper/offers.json

7. On the website, choose **Import JSON** and select `scraper/offers.json`.

The private `scraper/request.curl` file is ignored by Git. Check `git status`
before sharing your project to make sure it is not listed as a file to commit.
If WUSA rejects the request, your session may have expired: copy a fresh cURL
request and replace the contents of `scraper/request.curl`.

### Cookie setting alternative

If you already know how to copy the raw Cookie header, you can put just that
value in `WUSA_COOKIE=` in your private root `.env` file. Do not include the
cURL command, Python code, quotes, or the word `Cookie:`. The `.env.example`
file is a blank template; leave it blank and do not commit your `.env` file.
Create your private file with:

       if (-not (Test-Path .env)) { Copy-Item .env.example .env }

If you use this method, remove any old `scraper/request.curl` or
`scraper/request.py` file so the scraper reads the cookie from `.env`.

### Optional Gemini classification

Classification can use Gemini to read the offer and its linked page or poster
to identify the redemption type and any stated location. Add your Gemini key
to the private `.env` file as `GEMINI_API_KEY=your-key`, or use the Windows
key setup script below. The demo website does not use this key. Never put a
real key in `.env.example` or publish it.

## How the offer pipeline works

The scraper gets offers using your own WUSA session. Gemini can read the offer
and its linked page or poster to identify how it is redeemed and any stated
location. Nominatim looks up those locations. The result is saved in a JSON
file on your computer for you to import into the map.

Some linked pages require a sign-in or special browser features and may not be
readable. The scraper does not redeem offers or send your WUSA cookies to
Gemini.

## Optional monthly update on Windows

After configuring WUSA access and saving your Gemini key, run this once:

    .\scraper\install-monthly-task.ps1

Windows will update your local offers file at 9:00 a.m. on the first day of
each month while you are signed in. Check scraper/logs/ if an update fails.
WUSA cookies expire sometimes and may need to be replaced.

## Project files

- docs/ contains the website, sample offers, styles, and icons.
- scraper/ contains the Python scraper and location tools.
- .env.example is a blank settings template. Your private .env is not included
  in the public project.
- scraper/offers.json is created on your computer and ignored by Git.

GitHub Pages can host the demo from the docs folder; see
[GitHub's setup instructions](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site).
