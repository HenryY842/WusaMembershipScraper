
const map = L.map('map');

map.setView([43.4723, -80.5449], 14);

// Add OpenStreetMap tiles
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
}).addTo(map);

// Track user location
if (navigator.geolocation) {
    navigator.geolocation.watchPosition(success, error);
}

let marker, circle;
let zoomed = false;

function success(pos) {
    const lat = pos.coords.latitude;
    const lng = pos.coords.longitude;
    const accuracy = pos.coords.accuracy;

    if (marker) {
        map.removeLayer(marker);
        map.removeLayer(circle);
    }

    // Display user location
    marker = L.marker([lat, lng]).addTo(map);

    // Display accuracy circle
    circle = L.circle([lat, lng], {
        radius: accuracy
    }).addTo(map);

    // Zoom to user location only once
    if (!zoomed) {
        map.fitBounds(circle.getBounds());
        zoomed = true;
    }
}

function error(err) {
    console.info('User location unavailable; offer markers remain visible.', err.code);
}

async function loadOfferLocations() {
    const status = document.getElementById('map-status');
    const url = document.getElementById('map').dataset.offersUrl;
    try {
        const response = await fetch(url, { cache: 'no-store' });
        if (!response.ok) throw new Error(`Offers HTTP ${response.status}`);
        const data = await response.json();
        if (!Array.isArray(data.offers)) throw new Error('Missing offers array');
        const groups = new Map();
        let unresolved = 0;
        for (const offer of data.offers) {
            if (!['IN_PERSON', 'BOTH'].includes(offer.classification?.category)) continue;
            const places = offer.geocoded_locations || [];
            if (!places.length) unresolved += 1;
            for (const place of places) {
                if (place.status !== 'matched' || !Number.isFinite(place.lat) || !Number.isFinite(place.lon)
                    || Math.abs(place.lat) > 90 || Math.abs(place.lon) > 180) {
                    unresolved += 1;
                    continue;
                }
                const key = `${place.lat},${place.lon}`;
                if (!groups.has(key)) groups.set(key, []);
                groups.get(key).push({ offer, place });
            }
        }
        const markers = [];
        for (const entries of groups.values()) {
            const popup = document.createElement('div');
            for (const { offer, place } of entries) {
                const title = document.createElement('strong');
                title.textContent = offer.title;
                const address = document.createElement('p');
                address.textContent = place.display_name || place.address;
                popup.append(title, address);
                if (place.precision === 'building') {
                    const note = document.createElement('p');
                    note.textContent = 'Building location; the counter or floor is described in the offer.';
                    popup.append(note);
                }
            }
            const { lat, lon } = entries[0].place;
            markers.push(L.marker([lat, lon]).addTo(map).bindPopup(popup));
        }
        if (markers.length && !zoomed) {
            map.fitBounds(L.featureGroup(markers).getBounds(), { padding: [30, 30], maxZoom: 16 });
        }
        status.textContent = `${groups.size} mapped location(s). ${unresolved} location(s) need an address or match review.`;
    } catch (err) {
        status.textContent = 'Offer locations could not be loaded. Serve the project folder over HTTP and generate the offer coordinates first.';
        console.error(err);
    }
}

loadOfferLocations();
