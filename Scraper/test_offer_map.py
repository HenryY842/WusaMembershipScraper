"""Run the actual map script in a browser with deterministic map/data stubs."""

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class MapTests(unittest.TestCase):
    def test_saved_matches_are_grouped_unresolved_skipped_and_popup_text_escaped(self):
        browser = shutil.which("msedge") or "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
        if not Path(browser).exists():
            self.skipTest("Microsoft Edge is not installed")
        script = (Path(__file__).resolve().parent.parent / "Website/leafletMapScript.js").read_text(encoding="utf-8")
        matched = {"status": "matched", "lat": 43.47, "lon": -80.52, "display_name": "Business address"}
        data = {"offers": [
            {"title": "<img src=x onerror=alert(1)>", "classification": {"category": "IN_PERSON"}, "geocoded_locations": [matched]},
            {"title": "Other offer, same building", "classification": {"category": "BOTH"}, "geocoded_locations": [matched]},
            {"title": "Ambiguous", "classification": {"category": "IN_PERSON"}, "geocoded_locations": [{"status": "ambiguous"}]},
            {"title": "Online only", "classification": {"category": "ONLINE"}, "geocoded_locations": [matched]},
        ]}
        stub = """
            window.markerCount = 0;
            window.fitCalls = 0;
            window.setViewCalls = 0;
            window.popupCalls = 0;
            Object.defineProperty(navigator, 'geolocation', { value: {
                watchPosition(callback) { window.gpsCallback = callback; }
            } });
            window.L = {
                map: () => ({ setView() { window.setViewCalls += 1; }, fitBounds() { window.fitCalls += 1; }, removeLayer() {} }),
                tileLayer: () => ({ addTo() {} }),
                divIcon: (options) => { window.pinBadge = options.html; return options; },
                marker: () => ({ addTo() { window.markerCount += 1; return this; },
                                bindPopup(node) { document.body.append(node); return this; },
                                bindTooltip(node) { document.body.append(node); return this; },
                                openPopup() { window.popupCalls += 1; return this; } }),
                circle: () => ({ addTo() { return this; }, getBounds() { return []; } }),
                featureGroup: () => ({ getBounds() { return []; } })
            };
        """
        html = ('<!doctype html><div id="map-status"></div><button id="show-offers" disabled>Show offers</button><div id="map" data-offers-url="offers.json"></div><ul id="offer-locations"></ul>'
                + '<script>' + stub + '\nwindow.fetch = async () => ({ok:true,json:async () => ('
                + json.dumps(data) + ')});\n' + script
                + '''\nsetTimeout(() => {
                    document.body.dataset.markers = window.markerCount;
                    const beforeGps = window.fitCalls;
                    window.gpsCallback({coords:{latitude:44,longitude:-80,accuracy:10}});
                    document.body.dataset.gpsMovedMap = String(window.fitCalls !== beforeGps);
                    document.getElementById('show-offers').click();
                    document.body.dataset.refocused = String(window.fitCalls === beforeGps + 1);
                    document.body.dataset.badge = window.pinBadge;
                    const beforeFocus = window.setViewCalls;
                    document.querySelector('#offer-locations button').click();
                    document.body.dataset.offerFocused = String(window.setViewCalls === beforeFocus + 1 && window.popupCalls === 1);
                }, 100);</script>''')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            page = root / "map-test.html"
            page.write_text(html, encoding="utf-8")
            result = subprocess.run([
                browser, "--headless=new", "--disable-gpu", "--no-first-run",
                "--disable-background-networking", f"--user-data-dir={root / 'profile'}",
                "--dump-dom", "--virtual-time-budget=1000", page.as_uri(),
            ], capture_output=True, timeout=45)
            dom = result.stdout.decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace")[-1000:])
            self.assertIn('data-markers="1"', dom)
            self.assertIn("1/2 in-person offers and 1/1 online/in-person offers mapped across 1 locations. 1 location(s) need an address or match review.", dom)
            self.assertIn("&lt;img src=x onerror=alert(1)&gt;", dom)
            self.assertIn("Other offer, same building</strong>", dom)
            self.assertIn("Address found by Nominatim:</strong>", dom)
            self.assertIn("Business address</p>", dom)
            self.assertIn('data-gps-moved-map="false"', dom)
            self.assertIn('data-refocused="true"', dom)
            self.assertIn('data-offer-focused="true"', dom)
            self.assertIn('data-badge="&lt;span&gt;2&lt;/span&gt;"', dom)
            self.assertIn('Multiple possible matches; this address needs review.', dom)


if __name__ == "__main__":
    unittest.main()
