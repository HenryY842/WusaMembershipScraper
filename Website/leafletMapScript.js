const categoryInfo = {
    ONLINE: 'Online',
    IN_PERSON: 'In person',
    BOTH: 'All',
};
const map = L.map('map');
map.setView([43.4723, -80.5449], 14);
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
}).addTo(map);

let selectedCategory = 'IN_PERSON';
let allOffers = [];
let offerMarkers = [];
let markersByCoordinates = new Map();
let userMarker, accuracyCircle;
let offersLoaded = false;

function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
}
function isMapped(place) {
    return place && place.status === 'matched' && Number.isFinite(place.lat) && Number.isFinite(place.lon)
        && Math.abs(place.lat) <= 90 && Math.abs(place.lon) <= 180;
}
function coordinateKey(place) { return `${place.lat},${place.lon}`; }
function showOfferLocations() {
    if (offerMarkers.length) map.fitBounds(L.featureGroup(offerMarkers).getBounds(), { padding: [45, 45], maxZoom: 16 });
}
document.getElementById('show-offers').addEventListener('click', showOfferLocations);

const userLocationIcon = L.icon({
    iconUrl: 'icons/user-location.svg',
    className: 'user-location-dot',
    iconSize: [24, 24],
    iconAnchor: [12, 12],
    tooltipAnchor: [0, -12],
});

if (navigator.geolocation) {
    navigator.geolocation.watchPosition((position) => {
        const { latitude, longitude, accuracy } = position.coords;
        if (userMarker) { map.removeLayer(userMarker); map.removeLayer(accuracyCircle); }
        userMarker = L.marker([latitude, longitude], {
            icon: userLocationIcon, title: 'Your location', alt: 'Your location', zIndexOffset: 1000,
        }).addTo(map).bindTooltip(element('span', '', 'Your location'));
        accuracyCircle = L.circle([latitude, longitude], { radius: accuracy, color: '#4285f4', fillOpacity: 0.06, weight: 1 }).addTo(map);
        if (!offersLoaded && !offerMarkers.length) map.fitBounds(accuracyCircle.getBounds());
    }, (error) => console.info('User location unavailable; student offers remain visible.', error.code));
}

function conciseAddress(place) {
    const address = place.address_details || {};
    const street = [address.house_number, address.road].filter(Boolean).join(' ');
    const city = address.city || address.town || address.village;
    const state = address.state === 'Ontario' ? 'ON' : address.state;
    const parts = [place.precision === 'building' ? address.building || 'Student Life Centre' : street, city, state, address.postcode].filter(Boolean);
    return parts.length ? parts.join(', ') : place.display_name || place.address || 'Address not listed';
}
function safeLink(value) {
    try {
        const url = new URL(value);
        return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url : null;
    } catch { return null; }
}
function sourceLinks(offer, destination) {
    const links = [...new Set(offer.links || [])].map(safeLink).filter(Boolean);
    for (const url of links) {
        const wrapper = element('div', 'source-wrapper');
        const poster = /download_file|\.(pdf|png|jpe?g|webp)$/i.test(url.pathname);
        const link = element('a', 'source-link', poster ? 'Offer poster' : 'View offer');
        link.href = url.href;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        wrapper.append(link, element('p', 'source-host', url.hostname.replace(/^www\./, '')));
        destination.append(wrapper);
    }
    if (!links.length) destination.append(element('p', 'lookup-message', 'No link available.'));
}
function focusPlace(place) {
    map.setView([place.lat, place.lon], 17);
    markersByCoordinates.get(coordinateKey(place))?.openPopup();
    const reducedMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    document.querySelector('.map-frame').scrollIntoView({ behavior: reducedMotion ? 'auto' : 'smooth', block: 'start' });
}
function renderDestination(offer, destination) {
    if (selectedCategory === 'ONLINE' || offer.classification?.category === 'ONLINE') {
        sourceLinks(offer, destination);
        return;
    }
    const places = offer.geocoded_locations || [];
    for (const place of places) {
        const block = element('div', 'destination-place');
        const line = element('p', 'address-line');
        line.textContent = conciseAddress(place);
        block.append(line);
        if (place.precision === 'building') block.append(element('p', 'place-context', place.address));
        if (place.precision === 'address') block.append(element('p', 'place-context', 'Street-address location.'));
        if (isMapped(place)) {
            const button = element('button', 'map-link', 'Show on map');
            button.type = 'button';
            button.addEventListener('click', () => focusPlace(place));
            block.append(button);
        } else {
            block.append(element('p', 'lookup-message', place.status === 'ambiguous' ? 'Several possible locations. This address needs review.' : 'This location does not have a confirmed map pin yet.'));
        }
        destination.append(block);
    }
    if (!places.length) {
        const found = offer.classification?.addresses || offer.classification?.locations || [];
        for (const address of found) destination.append(element('p', 'address-line', address));
        destination.append(element('p', 'lookup-message', found.length ? 'Map location not confirmed.' : 'Address not listed.'));
    }
    sourceLinks(offer, destination);
}
function renderOfferList(offers) {
    const list = document.getElementById('offer-locations');
    list.replaceChildren();
    offers.forEach((offer) => {
        const row = element('li', 'offer-row');
        const info = element('div', 'offer-info');
        const copy = element('div', 'offer-copy');
        const details = Array.isArray(offer.details) ? offer.details : [];
        copy.append(element('strong', 'offer-name', offer.title));
        const description = details.filter((detail) => !/^(Category|Expires|Claimed):/.test(detail)).join(' ');
        copy.append(element('p', 'offer-description', description || 'See the offer for full details and redemption instructions.'));
        const expiry = details.find((detail) => detail.startsWith('Expires:'));
        if (expiry) copy.append(element('p', 'offer-expiry', 'Until ' + expiry.replace(/^Expires:\s*/, '')));
        info.append(copy);
        const destination = element('div', 'offer-destination');
        renderDestination(offer, destination);
        row.append(info, destination);
        list.append(row);
    });
    document.getElementById('offers-empty').hidden = offers.length !== 0;
}
function addPins(offers) {
    for (const pin of offerMarkers) map.removeLayer(pin);
    offerMarkers = [];
    markersByCoordinates = new Map();
    const groups = new Map();
    let mappedOffers = 0;
    let unresolved = 0;
    for (const offer of offers) {
        const places = selectedCategory === 'ONLINE' ? [] : offer.geocoded_locations || [];
        if (places.some(isMapped)) mappedOffers += 1;
        if (!places.length) unresolved += 1;
        for (const place of places) {
            if (!isMapped(place)) { unresolved += 1; continue; }
            const key = coordinateKey(place);
            if (!groups.has(key)) groups.set(key, []);
            groups.get(key).push({ offer, place });
        }
    }
    for (const [key, entries] of groups) {
        const popup = element('div', 'offer-popup');
        popup.append(element('p', 'popup-address', conciseAddress(entries[0].place)));
        for (const { offer, place } of entries) {
            const item = element('div', 'popup-item');
            item.append(element('strong', '', offer.title), element('p', '', place.address));
            if (place.precision === 'building') item.append(element('p', '', 'Building location; see the offer for the counter or floor.'));
            if (place.precision === 'address') item.append(element('p', '', 'Address location; the exact storefront has not been confirmed.'));
            popup.append(item);
        }
        const tooltip = element('span', '', entries.length > 1 ? `${conciseAddress(entries[0].place).split(',')[0]} · ${entries.length} offers` : entries[0].offer.title);
        const icon = L.divIcon({ className: 'offer-count-pin', html: `<span class="pin-face"><b>${entries.length}</b></span>`, iconSize: [34, 40], iconAnchor: [17, 40], popupAnchor: [0, -34] });
        const { lat, lon } = entries[0].place;
        const pin = L.marker([lat, lon], { icon, riseOnHover: true }).addTo(map).bindPopup(popup).bindTooltip(tooltip);
        offerMarkers.push(pin);
        markersByCoordinates.set(key, pin);
    }
    document.getElementById('show-offers').disabled = !offerMarkers.length;
    const status = document.getElementById('map-status');
    if (selectedCategory === 'ONLINE') status.textContent = `${offers.length} online ${offers.length === 1 ? 'offer' : 'offers'}.`;
    else status.textContent = `${mappedOffers}/${offers.length} offers mapped across ${groups.size} ${groups.size === 1 ? 'location' : 'locations'}.` + (unresolved ? ` ${unresolved} ${unresolved === 1 ? 'location needs' : 'locations need'} an address or match review.` : '');
    showOfferLocations();
}
function selectCategory(category) {
    if (!categoryInfo[category]) return;
    selectedCategory = category;
    for (const tab of document.querySelectorAll('[data-category]')) {
        const active = tab.dataset.category === category;
        tab.setAttribute('aria-selected', String(active));
        tab.tabIndex = active ? 0 : -1;
    }
    document.getElementById('offers-panel').setAttribute('aria-labelledby', `tab-${category}`);
    if (category === 'BOTH') {
        const physicalOffers = allOffers.filter((offer) => ['IN_PERSON', 'BOTH'].includes(offer.classification?.category));
        const onlineOffers = allOffers.filter((offer) => ['ONLINE', 'BOTH'].includes(offer.classification?.category));
        addPins(physicalOffers);
        renderOfferList(onlineOffers);
    } else {
        const offers = allOffers.filter((offer) => offer.classification?.category === category);
        addPins(offers);
        renderOfferList(offers);
    }
}
const tabs = [...document.querySelectorAll('[data-category]')];
for (const tab of tabs) {
    tab.addEventListener('click', () => selectCategory(tab.dataset.category));
    tab.addEventListener('keydown', (event) => {
        let index = tabs.indexOf(tab);
        if (event.key === 'ArrowRight') index = (index + 1) % tabs.length;
        else if (event.key === 'ArrowLeft') index = (index + tabs.length - 1) % tabs.length;
        else if (event.key === 'Home') index = 0;
        else if (event.key === 'End') index = tabs.length - 1;
        else return;
        event.preventDefault();
        tabs[index].focus();
        selectCategory(tabs[index].dataset.category);
    });
}
async function loadOffers() {
    try {
        const response = await fetch(document.getElementById('map').dataset.offersUrl, { cache: 'no-store' });
        if (!response.ok) throw new Error(`Offers HTTP ${response.status}`);
        const data = await response.json();
        if (!Array.isArray(data.offers)) throw new Error('Missing offers array');
        allOffers = data.offers;
        for (const count of document.querySelectorAll('[data-count]')) {
            count.textContent = allOffers.filter((offer) => count.dataset.count === 'BOTH'
                ? Object.hasOwn(categoryInfo, offer.classification?.category)
                : offer.classification?.category === count.dataset.count).length;
        }
        offersLoaded = true;
        selectCategory(selectedCategory);
    } catch (error) {
        document.getElementById('map-status').textContent = 'Your offers could not be loaded. Please try again shortly.';
        const empty = document.getElementById('offers-empty');
        empty.textContent = location.protocol === 'file:' ? 'Open this page through the local web server so it can read your saved offers.' : 'We could not load the saved offers. Refresh the page to try again.';
        empty.hidden = false;
        console.error(error);
    }
}
loadOffers();
