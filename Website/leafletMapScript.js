
const map = L.map('map');

map.setView([51.505, -0.09], 13);

// Add OpenStreetMap tiles
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
}).addTo(map);

// Track user location
navigator.geolocation.watchPosition(success, error);

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
    if (err.code === 1) {
        alert("Please allow geolocation access");
    } else {
        alert("Cannot get current location");
    }
}
