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

Use the scraper only with an account and offers you are authorized to access.
The demo map works without cookies or a Gemini key. WUSA cookies and Gemini
keys are private sign-in details: never publish them, commit them, or show
them in a video or screenshot.

### Add your WUSA cookies

1. Sign in to WUSA in Chrome and open your offers page.
2. Press **F12** to open Developer Tools, choose **Network**, and reload the
   offers page.
3. Select the request for the offers list. Open **Headers** and find **Cookie**
   under **Request Headers**. The cookie line contains pairs such as
   `cookie_name=cookie_value; another_name=another_value`.
4. In PowerShell, copy the starter to the private file the scraper reads:

       Copy-Item scraper/requests.example.py scraper/requests.py
       notepad scraper/requests.py

5. In `requests.py`, find this section:

       cookies = {
           # DELETE ME and paste your cookies here, as "cookie_name": "cookie_value",
       }

   Delete the `# DELETE ME...` comment. Add each cookie as a quoted name and
   value separated by a colon, with a comma between pairs. For the example
   Cookie line above, it would look like:

       cookies = {
           "cookie_name": "cookie_value",
           "another_name": "another_value",
       }

   Use your own names and values from the WUSA request. Do not paste the whole
   cURL command into this file. Cookies are private sign-in details; do not
   show or share them.
6. Install the Python packages:

       python -m pip install -r scraper/requirements.txt

7. Run the scraper. Add `--classify` if you also set up a Gemini key:

       python -m scraper.wusa_scraper --classify --output scraper/offers.json

8. On the website, choose **Import JSON** and select `scraper/offers.json`.

The scraper reads only the literal `headers` and `cookies` dictionaries in
`requests.py`; it does not run the file as a program. `requests.py` is ignored
by Git. Check `git status` before sharing your project to make sure your
private file is not listed to commit. If WUSA rejects the request, your cookies
may have expired; copy fresh ones into `requests.py`.

### Get and use a Gemini API key (optional)

You need a Gemini key only if you want the scraper to classify offers and read
linked offer pages or posters. The demo map does not need a key.

1. Open [Google AI Studio's API keys page](https://aistudio.google.com/apikey),
   sign in, choose **Create API key**, and copy the key.
2. Open this project folder in Visual Studio Code. Choose **Terminal**, then **New Terminal**. Make sure the terminal is using **PowerShell** and is open in the
   project folder.
3. Paste this command into the VS Code PowerShell terminal and press **Enter**:

       $env:GEMINI_API_KEY = Read-Host "Paste your Gemini API key"

4. When PowerShell asks for the key, paste it and press **Enter**. The key is
   set only for this terminal window; do not include it in a screenshot or
   recording.
5. Start classification by pasting this command into the same terminal and
   pressing **Enter**:

       python -m scraper.wusa_scraper --classify --output scraper/offers.json

   Keep the terminal open while it runs. When it finishes, the classified offers
   are saved in `scraper/offers.json`. If it says a package is missing, install
   the packages with `python -m pip install -r scraper/requirements.txt` and run
   the scraper command again.
6. Open the map in your browser, choose **Import JSON**, and select
   `scraper/offers.json`.
7. When finished, remove the key from that PowerShell terminal:

       Remove-Item Env:GEMINI_API_KEY

Before running the scraper, set up your WUSA cookies as described above. For the
optional monthly task, save the key encrypted for your Windows account and
install the task from PowerShell:

       powershell -ExecutionPolicy Bypass -File .\scraper\setup-gemini-key.ps1
       powershell -ExecutionPolicy Bypass -File .\scraper\install-monthly-task.ps1

## How the offer pipeline works

The scraper gets offers using your own WUSA session. Gemini can read the offer
and its linked page or poster to identify how it is redeemed and any stated
location. Nominatim looks up those locations. The result is saved in a JSON
file on your computer for you to import into the map.

Some linked pages require a sign-in or special browser features and may not be
readable. The scraper does not redeem offers or send your WUSA cookies to
Gemini.

## Optional monthly update on Windows

After copying your WUSA cookies into `scraper/requests.py` and saving your key
with the encrypted setup script, run this once:

    powershell -ExecutionPolicy Bypass -File .\scraper\install-monthly-task.ps1

Windows will update your local offers file at 9:00 a.m. on the first day of
each month while you are signed in. Check scraper/logs/ if an update fails.
WUSA cookies expire sometimes and may need to be replaced.

## Project files

- docs/ contains the website, sample offers, styles, and icons.
- scraper/ contains the Python scraper and location tools.
- scraper/requests.example.py is the starter, with no real cookies, for your private
  scraper/requests.py file.
- scraper/offers.json is created on your computer and ignored by Git.

GitHub Pages can host the demo from the docs folder; see
[GitHub's setup instructions](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site).
