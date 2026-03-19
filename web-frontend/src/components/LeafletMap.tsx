import React, { useEffect, useRef } from 'react';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';

// Leaflet requires these icon fixups when grouped with React bundlers
import icon from 'leaflet/dist/images/marker-icon.png';
import iconShadow from 'leaflet/dist/images/marker-shadow.png';

let DefaultIcon = L.icon({
    iconUrl: icon,
    shadowUrl: iconShadow
});
L.Marker.prototype.options.icon = DefaultIcon;

interface LeafletMapProps {
    heatmapData: number[][]; // Not heavily used currently, but kept for signature
}

export default function LeafletMap({ heatmapData }: LeafletMapProps) {
    const mapRef = useRef<HTMLDivElement>(null);
    const mapInstance = useRef<L.Map | null>(null);

    // Initialize Map and Load GeoJSON
    useEffect(() => {
        if (!mapRef.current) return;

        // Only initialize once
        if (!mapInstance.current) {
            // Center around Connaught Place, New Delhi
            mapInstance.current = L.map(mapRef.current, { zoomControl: false }).setView([28.6139, 77.2090], 11);

            L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
                attribution: '&copy; OpenStreetMap contributors'
            }).addTo(mapInstance.current);

            // Fetch and render the Ward polygons
            fetch('/delhi_wards.geojson')
                .then(res => res.json())
                .then(data => {
                    if (mapInstance.current) {
                        L.geoJSON(data, {
                            style: function (feature) {
                                // Randomly assign Poor/Severe colors based on geometry for the hackathon demo
                                const isSevere = Math.random() > 0.6;
                                return {
                                    color: isSevere ? "#ef4444" : "#69f6b8", // Tailwind error red / secondary green
                                    weight: 2,
                                    fillOpacity: isSevere ? 0.2 : 0.05
                                };
                            },
                            onEachFeature: function (feature, layer) {
                                if (feature.properties && feature.properties.name) {
                                    layer.bindPopup(`<b>${feature.properties.name}</b><br/>Ward Border`);
                                }
                            }
                        }).addTo(mapInstance.current);
                    }
                })
                .catch(err => console.error("Error loading ward geojson:", err));
        }

        return () => {
            if (mapInstance.current) {
                mapInstance.current.remove();
                mapInstance.current = null;
            }
        };
    }, []);

    return (
        <div
            ref={mapRef}
            style={{ height: '100vh', width: '100vw', position: 'absolute', top: 0, left: 0 }}
        />
    );
}
