"""Check category filtering, map interactions, and responsive layout in a Chromium browser."""
import json
from contextlib import contextmanager
import itertools
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
from bs4 import BeautifulSoup

@contextmanager
def edge_page(browser, width, height):
    """Use an exact viewport; Edge otherwise clamps narrow headless windows."""
    from websockets.sync.client import connect
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profile:
        process = subprocess.Popen([
            browser, '--headless=new', '--disable-gpu', '--no-first-run', '--disable-background-networking',
            '--remote-debugging-port=0', f'--user-data-dir={profile}', 'about:blank',
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            port_file = Path(profile) / 'DevToolsActivePort'
            deadline = time.monotonic() + 10
            while not port_file.exists():
                if process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError('Headless Edge failed to start')
                time.sleep(.05)
            port, path = port_file.read_text().splitlines()[:2]
            with connect(f'ws://127.0.0.1:{port}{path}', proxy=None, max_size=None) as connection:
                ids = itertools.count(1)
                session = None

                def command(method, params=None):
                    message = {'id': next(ids), 'method': method, 'params': params or {}}
                    if session and method.split('.')[0] in {'Page', 'Runtime', 'Emulation'}:
                        message['sessionId'] = session
                    connection.send(json.dumps(message))
                    while True:
                        response = json.loads(connection.recv(timeout=20))
                        if response.get('id') == message['id']:
                            if 'error' in response:
                                raise RuntimeError(response['error'])
                            return response.get('result', {})

                target = command('Target.createTarget', {'url': 'about:blank'})['targetId']
                session = command('Target.attachToTarget', {'targetId': target, 'flatten': True})['sessionId']
                command('Emulation.setDeviceMetricsOverride', {'width': width, 'height': height, 'deviceScaleFactor': 1, 'mobile': width < 620})
                command('Page.enable')
                try:
                    yield command
                finally:
                    try:
                        command('Browser.close')
                    except Exception:
                        pass
        finally:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=5)

class MapTests(unittest.TestCase):
    def test_category_tabs_map_actions_links_and_responsive_layout(self):
        browser = os.environ.get('WUSA_CHROMIUM_BROWSER') or shutil.which('msedge') or 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
        if not Path(browser).exists():
            self.skipTest('Microsoft Edge is not installed')
        website = Path(__file__).resolve().parents[2] / 'docs'
        matched = {'status': 'matched', 'lat': 43.47, 'lon': -80.52, 'display_name': 'Business address'}
        data = {'generated_at': '2026-11-06T05:00:00Z', 'offers': [
            {'title': '<img src=x onerror=alert(1)>', 'details': ['A student discount.', 'Expires: November 30, 2026'], 'claimed': False, 'links': ['https://example.com/poster.pdf'], 'classification': {'category': 'IN_PERSON'}, 'geocoded_locations': [matched]},
            {'title': 'Other offer, same building', 'classification': {'category': 'IN_PERSON'}, 'geocoded_locations': [matched]},
            {'title': 'Ambiguous', 'classification': {'category': 'IN_PERSON'}, 'geocoded_locations': [{'status': 'ambiguous', 'address': 'Unconfirmed address'}]},
            {'title': 'Both offer', 'details': ['Claimed: Yes'], 'classification': {'category': 'BOTH'}, 'links': ['https://example.com/both'], 'geocoded_locations': [matched]},
            {'title': 'Online only', 'classification': {'category': 'ONLINE'}, 'links': ['https://example.com/discount', 'javascript:alert(1)'], 'geocoded_locations': [{**matched, 'lat': 40, 'lon': -70}]},
            {'title': 'Not classified yet'},
        ]}
        stub = '''
            window.visibleMarkers = [];
            window.fitCalls = 0;
            window.setViewCalls = 0;
            window.popupCalls = 0;
            Object.defineProperty(navigator, 'geolocation', {value: {watchPosition(callback) { window.gpsCallback = callback; }}});
            window.L = {
                map: () => ({setView() { window.setViewCalls++; }, fitBounds() { window.fitCalls++; }, removeLayer(layer) { window.visibleMarkers = window.visibleMarkers.filter(item => item !== layer); }}),
                tileLayer: () => ({addTo() {}}),
                icon: options => options,
                divIcon: options => options,
                marker: (coords, options = {}) => ({coords, options, addTo() { window.visibleMarkers.push(this); return this; }, bindPopup(node) { this.popup = node; return this; }, bindTooltip() { return this; }, openPopup() { window.popupCalls++; return this; }}),
                circle: () => ({addTo() {return this;}, getBounds() {return [];}}),
                featureGroup: () => ({getBounds() {return [];}})
            };
        '''
        checks = '''
            setTimeout(async () => {
                const report = {};
                const pins = () => window.visibleMarkers.filter(marker => marker.options.icon?.className === 'offer-count-pin');
                const people = () => window.visibleMarkers.filter(marker => marker.options.icon?.className === 'user-location-dot');
                report.initialRows = document.querySelectorAll('.offer-row').length;
                report.initialStatus = document.getElementById('map-status').textContent;
                report.initialPins = pins().length;
                report.badge = pins()[0].options.icon.html;
                report.popupAddress = pins()[0].popup.textContent.includes('Business address');
                report.mapClaimStatus = pins()[0].popup.textContent.includes('Not claimed');
                report.expiryVisible = document.querySelector('.offer-expiry').textContent;
                report.safeTitle = document.querySelector('.offer-name').textContent;
                report.noInjectedImages = document.querySelectorAll('.offer-list img').length === 0;
                const beforeGps = window.fitCalls;
                window.gpsCallback({coords:{latitude:44,longitude:-80,accuracy:10}});
                report.personIcon = people()[0]?.options.icon.iconUrl;
                report.personLabel = people()[0]?.options.alt;
                window.gpsCallback({coords:{latitude:44.01,longitude:-80.01,accuracy:12}});
                report.personCount = people().length;
                report.personCoordinates = people()[0]?.coords;
                report.gpsMovedMap = window.fitCalls !== beforeGps;
                document.getElementById('show-offers').click();
                report.refocused = window.fitCalls === beforeGps + 1;
                const beforeFocus = window.setViewCalls;
                document.querySelector('.map-link').click();
                report.offerFocused = window.setViewCalls === beforeFocus + 1 && window.popupCalls === 1;
                document.getElementById('tab-ONLINE').click();
                report.onlineRows = document.querySelectorAll('.offer-row').length;
                report.onlinePins = pins().length;
                report.onlinePeople = people().length;
                report.onlineStatus = document.getElementById('map-status').textContent;
                report.onlineResetDisabled = document.getElementById('show-offers').disabled;
                report.onlineLinks = [...document.querySelectorAll('.source-link')].map(link => ({href:link.href, rel:link.rel}));
                report.onlineOverflow = document.documentElement.scrollWidth > window.innerWidth;
                document.getElementById('tab-ONLINE').dispatchEvent(new KeyboardEvent('keydown', {key:'ArrowRight', bubbles:true}));
                document.getElementById('tab-IN_PERSON').dispatchEvent(new KeyboardEvent('keydown', {key:'ArrowRight', bubbles:true}));
                report.bothSelected = document.getElementById('tab-BOTH').getAttribute('aria-selected');
                report.bothRows = document.querySelectorAll('.offer-row').length;
                report.bothTitle = document.querySelector('.offer-name').textContent;
                report.bothTitles = [...document.querySelectorAll('.offer-name')].map(node => node.textContent);
                report.claimStatuses = [...document.querySelectorAll('.offer-claim-status')].map(node => node.textContent);
                report.bothPins = pins().length;
                report.bothBadge = pins()[0].options.icon.html;
                report.bothPopup = pins()[0].popup.textContent;
                report.bothStatus = document.getElementById('map-status').textContent;
                report.bothOnlineLinks = [...document.querySelectorAll('.source-link')].map(link => link.href);
                report.firstOfferMapLinks = document.querySelectorAll('.offer-row')[0].querySelectorAll('.map-link').length;
                report.panelLabel = document.getElementById('offers-panel').getAttribute('aria-labelledby');
                document.getElementById('tab-IN_PERSON').click();
                report.overflow = document.documentElement.scrollWidth > window.innerWidth;
                report.tabCounts = [...document.querySelectorAll('[data-count]')].map(node => node.textContent);
                report.noExtraSections = !document.querySelector('header, footer, aside, h1, h2');
                report.categoryIconsLoaded = [...document.querySelectorAll('.category-icon')].length === 2 && [...document.querySelectorAll('.category-icon')].every(icon => icon.complete && icon.naturalWidth > 0);
                const importedFile = new File([JSON.stringify({offers:[{title:'Local import', details:[], links:[], classification:{category:'ONLINE'}}]})], 'local.json', {type:'application/json'});
                const transfer = new DataTransfer(); transfer.items.add(importedFile);
                const input = document.getElementById('offers-file'); input.files = transfer.files;
                input.dispatchEvent(new Event('change', {bubbles:true}));
                await new Promise(resolve => setTimeout(resolve, 30));
                report.importStatus = document.getElementById('data-source-status').textContent;
                report.importAllSelected = document.getElementById('tab-BOTH').getAttribute('aria-selected');
                report.importRows = document.querySelectorAll('.offer-row').length;
                document.getElementById('load-demo').click();
                await new Promise(resolve => setTimeout(resolve, 30));
                report.demoRestored = document.getElementById('data-source-status').textContent === 'Demo data';
                report.demoRowsRestored = document.querySelectorAll('.offer-row').length;
                const output = document.createElement('pre'); output.id = 'qa-results'; output.textContent = JSON.stringify(report); document.body.append(output);
            }, 100);
        '''
        soup = BeautifulSoup((website / 'index.html').read_text(encoding='utf-8-sig'), 'html.parser')
        for node in soup.select('script, link'):
            node.decompose()
        for icon in soup.select('.category-icon'):
            icon['src'] = (website / icon['src']).as_uri()
        style = soup.new_tag('style')
        style.string = (website / 'style.css').read_text(encoding='utf-8-sig')
        soup.head.append(style)
        script = soup.new_tag('script')
        script.string = (stub + '\nwindow.fetch = async () => ({ok:true,json:async () => (' + json.dumps(data) + ')});\n'
                         + (website / 'script.js').read_text(encoding='utf-8-sig') + checks)
        soup.body.append(script)
        for width in (1440, 390):
            with self.subTest(width=width), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                page = root / 'map-test.html'
                page.write_text(str(soup), encoding='utf-8')
                with edge_page(browser, width, 1000) as command:
                    command('Page.navigate', {'url': page.as_uri()})
                    result = command('Runtime.evaluate', {
                        'expression': '''new Promise(resolve => { let tries = 0; const timer = setInterval(() => {
                            const output = document.getElementById('qa-results');
                            if (output || tries++ > 60) { clearInterval(timer); resolve(output ? JSON.parse(output.textContent) : null); }
                        }, 50); })''', 'awaitPromise': True, 'returnByValue': True, 'timeout': 5000,
                    })
                    report = result.get('result', {}).get('value')
                self.assertIsNotNone(report, 'Map script failed to finish browser checks')
                self.assertEqual(report['initialRows'], 3)
                self.assertEqual(report['initialPins'], 1)
                self.assertIn('2/3 offers mapped across 1 location.', report['initialStatus'])
                self.assertIn('<b>2</b>', report['badge'])
                self.assertTrue(report['popupAddress'])
                self.assertTrue(report['mapClaimStatus'])
                self.assertEqual(report['safeTitle'], '<img src=x onerror=alert(1)>')
                self.assertTrue(report['noInjectedImages'])
                self.assertIn('November 30, 2026', report['expiryVisible'])
                self.assertFalse(report['gpsMovedMap'])
                self.assertEqual(report['personIcon'], 'icons/user-location.svg')
                self.assertEqual(report['personLabel'], 'Your location')
                self.assertEqual(report['personCount'], 1)
                self.assertEqual(report['personCoordinates'], [44.01, -80.01])
                self.assertTrue(report['categoryIconsLoaded'])
                self.assertTrue(report['refocused'])
                self.assertTrue(report['offerFocused'])
                self.assertEqual(report['onlineRows'], 1)
                self.assertEqual(report['onlinePins'], 0)
                self.assertEqual(report['onlinePeople'], 1)
                self.assertEqual(report['onlineStatus'], '1 online offer.')
                self.assertTrue(report['onlineResetDisabled'])
                self.assertEqual(len(report['onlineLinks']), 1)
                self.assertEqual(report['onlineLinks'][0]['href'], 'https://example.com/discount')
                self.assertIn('noopener', report['onlineLinks'][0]['rel'])
                self.assertEqual(report['bothSelected'], 'true')
                self.assertEqual(report['bothRows'], 6)
                self.assertEqual(report['bothTitle'], '<img src=x onerror=alert(1)>')
                self.assertEqual(report['bothTitles'], ['<img src=x onerror=alert(1)>', 'Other offer, same building', 'Ambiguous', 'Both offer', 'Online only', 'Not classified yet'])
                self.assertEqual(report['claimStatuses'], ['Not claimed', 'Already claimed'])
                self.assertEqual(report['bothPins'], 1)
                self.assertIn('<b>3</b>', report['bothBadge'])
                self.assertIn('Other offer, same building', report['bothPopup'])
                self.assertIn('Both offer', report['bothPopup'])
                self.assertNotIn('Online only', report['bothPopup'])
                self.assertIn('3/4 offers mapped across 1 location.', report['bothStatus'])
                self.assertEqual(report['bothOnlineLinks'], ['https://example.com/poster.pdf', 'https://example.com/both', 'https://example.com/discount'])
                self.assertEqual(report['firstOfferMapLinks'], 1)
                self.assertEqual(report['panelLabel'], 'tab-BOTH')
                self.assertEqual(report['tabCounts'], ['1', '3', '6'])
                self.assertTrue(report['noExtraSections'])
                self.assertFalse(report['overflow'])
                self.assertFalse(report['onlineOverflow'])
                self.assertEqual(report['importStatus'], 'Imported local.json')
                self.assertEqual(report['importAllSelected'], 'true')
                self.assertEqual(report['importRows'], 1)
                self.assertTrue(report['demoRestored'])
                self.assertEqual(report['demoRowsRestored'], 3)

if __name__ == '__main__':
    unittest.main()
