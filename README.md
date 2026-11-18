# WUSA Rewards Map

A simple map for browsing student offers.

## Try the demo

**The sample website needs no WUSA cookies, Gemini key, or Python packages.**
It starts with made-up sample offers, so you can try it without signing in or
connecting to WUSA.

If you downloaded this project, open PowerShell in its folder and run:

    python -m http.server 8000

Then open http://localhost:8000/docs/ in your browser. Leave the PowerShell
window open while you use the page.

Do not double-click docs/index.html or use GitHub's code preview; those do not
run the demo page. Use the local address above or publish the docs folder with
GitHub Pages.

Choose **Online**, **In person**, or **All** to browse the sample. Choose
**Import JSON** to select an offers file on your computer. The file is read by
your browser and is not uploaded. Choose **Demo data** to return to the sample.

## Use your own WUSA offers (optional)

Only do this if you are authorized to access the offers. Your cookies and API
key are private. Do not post them on GitHub or send them to anyone.

1. Install Python packages:

       python -m pip install -r scraper/requirements.txt

2. Copy the example settings file, then open your private copy:

       if (-not (Test-Path .env)) { Copy-Item .env.example .env }
       notepad .env

3. Add your own WUSA cookie to WUSA_COOKIE. If you prefer, save your signed-in
   browser request as scraper/request.curl instead. Keep both files private;
   Git ignores them.

4. Add your own Gemini key to GEMINI_API_KEY if you want the program to read
   offer pages and posters and sort offers by type. The demo website does not
   use this key. The Windows key setup also stores it encrypted for the monthly
   task:

       .\scraper\setup-gemini-key.ps1

5. Create your local offers file:

       python -m scraper.wusa_scraper --classify --output scraper/offers.json

6. On the website, choose **Import JSON** and select scraper/offers.json.

The site always starts with the made-up demo offers. It never loads your real
offers automatically.

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

## Recording a short guide

A simple screen-recording outline is in [docs/video-walkthrough.md](docs/video-walkthrough.md).
GitHub Pages can host the demo from the docs folder; see
[GitHub's setup instructions](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site).
