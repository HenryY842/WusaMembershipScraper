# WUSA Rewards Map

## Try the demo

The sample website uses made-up offers. You do not need WUSA cookies, a Gemini
key, or Python packages to try it.

On Windows, double-click `start-demo.bat` in the project folder. Leave the
terminal window open, then visit <http://localhost:8000/docs/>. Press **Ctrl+C**
in the terminal when you are done.

Or, open PowerShell in the project folder and run:

    python -m http.server 8000

Then visit <http://localhost:8000/docs/> and leave PowerShell open while you use
the map.

Do not double-click `docs/index.html` or use GitHub's code preview; those do not
run the demo page. You can also publish the `docs` folder with GitHub Pages.

Choose **Online**, **In person**, or **All** to browse the sample. **All** puts
every offer in the list and shows in-person offers on the map. If an imported
offer includes a claimed value, the list and map popup show whether it is
already claimed. Claim status reflects the imported file; scrape and import
again after claiming or unclaiming an offer. Choose **Import JSON** to select
an offers file on your computer. Your browser reads the file locally; it is
not uploaded. Choose **Demo data** to return to the sample.

## Use your own WUSA offers (optional)

Only use the scraper with an account and offers you are authorized to access.
Keep WUSA cookies and Gemini API keys private. Do not commit or share them. The
public starter file contains no real credentials. If a cookie or key is exposed,
refresh or revoke it with the service that issued it.

### Add your WUSA cookies

1. Sign in to WUSA in Chrome and open your offers page.
2. Press **F12** to open Developer Tools, choose **Network**, and reload the
   offers page.
3. Find the WUSA offers request, right-click it, and choose **Copy as cURL
   (bash)**.
4. Open [curlconverter.com](https://curlconverter.com/), choose **Python
   requests**, and paste the copied cURL command into the converter. Copy the
   complete Python output it creates. The output contains your WUSA cookies, so
   treat it like a password. The converter says it processes the command in
   your browser, but never share the command or its output.
5. Open `scraper/requests.example.py` in Visual Studio Code. Select and delete
   its starter text, then paste the **whole Python output** from curlconverter,
   including the `cookies = {...}` and `headers = {...}` dictionaries. Save
   the file. The scraper reads cookies and headers directly from this file.

The example file shows the expected dictionary order:

    cookies = {
        # DELETE ME and paste your cookies here
    }

    headers = {
        # DELETE ME and paste your headers here
    }

The scraper reads the literal `cookies` and `headers` dictionaries from
`requests.example.py`; it does not run the converted request code. This is a
tracked example file, so adding cookies to it changes a file in the project.
Never commit or share the file while it contains cookies. Before publishing,
restore the starter contents with `git restore -- scraper/requests.example.py`
from a Git checkout, or download a fresh copy of the starter file. Do not show
the cURL command, converter output, or cookie values in a video or screenshot.
If WUSA rejects your request, your cookies may have expired; copy a fresh
request and replace the contents of `requests.example.py`.

After extracting the ZIP, check whether it created two nested project folders
with the same name. If so, move the inner folder out of the outer folder (rename
it if Windows says that name is already in use). Open the folder that directly
contains `README.md`, `docs/`, and `scraper/` in Visual Studio Code.

In the VS Code PowerShell terminal, install the Python packages from that
project folder:

    python -m pip install -r .\scraper\requirements.txt

To create an offers file without Gemini classification, run:

    python -m scraper.wusa_scraper --output scraper/offers.json

Then, on the website, choose **Import JSON** and select `scraper/offers.json`.

### Add Gemini classification (optional)

You only need a Gemini key if you want the scraper to classify offers and read
linked offer pages or posters. The demo website does not use this key.

1. Open [Google AI Studio's API keys page](https://aistudio.google.com/apikey),
   sign in, choose **Create API key**, and copy the key.
2. Open this project folder in Visual Studio Code. Choose **Terminal**, then
   **New Terminal**. Make sure it is using **PowerShell** and is open in the
   project folder.
3. Paste this command into the VS Code PowerShell terminal and press **Enter**:

       $env:GEMINI_API_KEY = Read-Host "Paste your Gemini API key"

4. When PowerShell asks for the key, paste it and press **Enter**. PowerShell
   shows the text you enter, so do this in a private terminal and do not record
   or share the screen.
5. In the same terminal, run:

       python -m scraper.wusa_scraper --classify --output scraper/offers.json

Keep the terminal open while the scraper runs. When it finishes, import
`scraper/offers.json` into the map using **Import JSON**. If Python reports a
missing package, install the packages using the command above and rerun the
scraper.

When finished, remove the key from that PowerShell terminal and close it:

    Remove-Item Env:GEMINI_API_KEY

For the optional monthly task, save the key encrypted for your Windows account
and install the task from PowerShell:

    powershell -ExecutionPolicy Bypass -File .\scraper\setup-gemini-key.ps1
    powershell -ExecutionPolicy Bypass -File .\scraper\install-monthly-task.ps1

## How the offer program works

The scraper gets offers using your WUSA session cookies. Gemini can read an
offer and its linked page or poster to identify how it is redeemed and any
stated location. Nominatim looks up those locations. The result is saved in a
JSON file on your computer for you to import into the map.

Some linked pages require a sign-in or special browser features and may not
be readable. The scraper does not redeem offers or send your WUSA cookies to
Gemini.

## Optional monthly update on Windows

After adding cookies to `scraper/requests.example.py` and saving your key with the
encrypted setup script, install the scheduled task with:

    powershell -ExecutionPolicy Bypass -File .\scraper\install-monthly-task.ps1

Windows updates your local offers file at 9:00 a.m. on the first day of each
month while you are signed in. Check `scraper/logs/` if an update fails. WUSA
cookies expire sometimes and may need to be replaced.

## Project files

- `docs/` contains the demo website, sample offers, styles, and icons.
- `scraper/` contains the Python scraper and location tools.
- `scraper/requests.example.py` is where you paste your WUSA cookies and
  request headers for local scraping. Restore its starter contents before
  publishing or sharing the project.
- `scraper/offers.json` is created on your computer and ignored by Git.

GitHub Pages can publish the demo from the `docs` folder. See [GitHub's Pages
setup instructions](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site).
