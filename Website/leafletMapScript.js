
const map = L.map('map');

map.setView([43.4723, -80.5449], 14);

// Add OpenStreetMap tiles
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
}).addTo(map);

let marker, circle;
let zoomed = false;
let offerMarkers = [];

// Track user location without moving away from the displayed business pins.
if (navigator.geolocation) {
    navigator.geolocation.watchPosition(success, error);
}

function showOfferLocations() {
    if (offerMarkers.length) {
        map.fitBounds(L.featureGroup(offerMarkers).getBounds(), { padding: [30, 30], maxZoom: 16 });
        zoomed = true;
    }
}

document.getElementById('show-offers').addEventListener('click', showOfferLocations);

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

function isMapped(place) {
    return place.status === 'matched' && Number.isFinite(place.lat) && Number.isFinite(place.lon)
        && Math.abs(place.lat) <= 90 && Math.abs(place.lon) <= 180;
}

function renderOfferList(offers, markersByCoordinates) {
    const list = document.getElementById('offer-locations');
    list.replaceChildren();
    for (const offer of offers) {
        if (!['IN_PERSON', 'BOTH'].includes(offer.classification?.category)) continue;
        const row = document.createElement('li');
        const title = document.createElement('strong');
        title.textContent = offer.title;
        const category = document.createElement('span');
        category.textContent = offer.classification.category === 'BOTH' ? ' — Online and in person' : ' — In person';
        row.append(title, category);
        const places = offer.geocoded_locations || [];
        if (!places.length) {
            const message = document.createElement('p');
            message.textContent = 'No physical address found yet.';
            row.append(message);
        }
        for (const place of places) {
            const address = document.createElement('p');
            address.textContent = place.display_name || place.address || 'Address unavailable';
            row.append(address);
            if (isMapped(place)) {
                const button = document.createElement('button');
                button.type = 'button';
                button.textContent = 'Show on map';
                button.addEventListener('click', () => {
                    map.setView([place.lat, place.lon], 17);
                    markersByCoordinates.get(`${place.lat},${place.lon}`).openPopup();
                });
                row.append(button);
            } else {
                const message = document.createElement('p');
                message.textContent = place.status === 'ambiguous'
                    ? 'Multiple possible matches; this address needs review.'
                    : 'This location has no confirmed map match yet.';
                row.append(message);
            }
        }
        list.append(row);
    }
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
        const totals = { IN_PERSON: 0, BOTH: 0 };
        const mapped = { IN_PERSON: 0, BOTH: 0 };
        let unresolved = 0;
        for (const offer of data.offers) {
            if (!['IN_PERSON', 'BOTH'].includes(offer.classification?.category)) continue;
            const category = offer.classification.category;
            totals[category] += 1;
            const places = offer.geocoded_locations || [];
            if (places.some(isMapped)) mapped[category] += 1;
            if (!places.length) unresolved += 1;
            for (const place of places) {
                if (!isMapped(place)) {
                    unresolved += 1;
                    continue;
                }
                const key = `${place.lat},${place.lon}`;
                if (!groups.has(key)) groups.set(key, []);
                groups.get(key).push({ offer, place });
            }
        }
        const markers = [];
        const markersByCoordinates = new Map();
        for (const entries of groups.values()) {
            const popup = document.createElement('div');
            const addressLabel = document.createElement('strong');
            addressLabel.textContent = 'Address found by Nominatim:';
            const address = document.createElement('p');
            address.textContent = entries[0].place.display_name || entries[0].place.address;
            popup.append(addressLabel, address);
            for (const { offer, place } of entries) {
                const title = document.createElement('strong');
                title.textContent = offer.title;
                const offerLocation = document.createElement('p');
                offerLocation.textContent = place.address;
                popup.append(title, offerLocation);
                if (place.precision === 'building') {
                    const note = document.createElement('p');
                    note.textContent = 'Building location; the counter or floor is described in the offer.';
                    popup.append(note);
                } else if (place.precision === 'address') {
                    const note = document.createElement('p');
                    note.textContent = 'Street-address location; the exact storefront has not been confirmed.';
                    popup.append(note);
                }
            }
            const { lat, lon } = entries[0].place;
            const tooltip = document.createElement('span');
            const locationName = (entries[0].place.display_name || entries[0].place.address || '').split(',')[0];
            tooltip.textContent = entries.length > 1 ? `${locationName} (${entries.length} offers)` : entries[0].offer.title;
            const icon = L.divIcon({
                className: 'offer-count-pin',
                html: `<span>${entries.length}</span>`,
                iconSize: [34, 36], iconAnchor: [17, 36], popupAnchor: [0, -32],
            });
            const pin = L.marker([lat, lon], { icon }).addTo(map).bindPopup(popup).bindTooltip(tooltip);
            markers.push(pin);
            markersByCoordinates.set(`${lat},${lon}`, pin);
        }
        offerMarkers = markers;
        document.getElementById('show-offers').disabled = !markers.length;
        showOfferLocations();
        renderOfferList(data.offers, markersByCoordinates);
        status.textContent = `${mapped.IN_PERSON}/${totals.IN_PERSON} in-person offers and ${mapped.BOTH}/${totals.BOTH} online/in-person offers mapped across ${groups.size} locations. ${unresolved} location(s) need an address or match review.`;
    } catch (err) {
        status.textContent = 'Offer locations could not be loaded. Serve the project folder over HTTP and generate the offer coordinates first.';
        console.error(err);
    }
}

loadOfferLocations();
