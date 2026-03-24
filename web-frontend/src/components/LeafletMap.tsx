import React, { useEffect, useRef } from 'react';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
// @ts-ignore
import 'leaflet-velocity';
import 'leaflet-velocity/dist/leaflet-velocity.css';

import icon from 'leaflet/dist/images/marker-icon.png';
import iconShadow from 'leaflet/dist/images/marker-shadow.png';

let DefaultIcon = L.icon({
    iconUrl: icon,
    shadowUrl: iconShadow,
    iconSize: [25, 41],
    iconAnchor: [12, 41]
});
L.Marker.prototype.options.icon = DefaultIcon;

interface LeafletMapProps {
    wards: any[];
    selectedWard: any | null;
    onWardClick: (ward: any) => void;
    granularity: 'ward' | 'district';
}

export default function LeafletMap({ wards, selectedWard, onWardClick, granularity }: LeafletMapProps) {
    const mapRef = useRef<HTMLDivElement>(null);
    const mapInstance = useRef<L.Map | null>(null);
    const geoJsonLayer = useRef<L.GeoJSON | null>(null);

    // 1. Initialize Map once
    useEffect(() => {
        if (!mapRef.current) return;
        if (!mapInstance.current) {
            mapInstance.current = L.map(mapRef.current, { zoomControl: false }).setView([28.6139, 77.2090], 11);
            // Switched to Military-Grade Deep Dark Matter rendering layer
            L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
                attribution: '&copy; OpenStreetMap contributors'
            }).addTo(mapInstance.current);
            L.control.zoom({ position: 'bottomright' }).addTo(mapInstance.current);
            
            // ─── HACKATHON EDGE: Live Wind Particle Engine ───
            const API_BASE = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";
            fetch(`${API_BASE}/api/v1/dashboard/weather/wind-grid`)
                .then(res => res.json())
                .then(data => {
                    // @ts-ignore
                    const velocityLayer = L.velocityLayer({
                        displayValues: false,
                        displayOptions: {
                            velocityType: 'Global Wind',
                            displayPosition: 'bottomleft',
                            displayEmptyString: 'No wind data'
                        },
                        data: data,
                        maxVelocity: 15,
                        velocityScale: 0.05,
                        colorScale: ["#1e3a8a", "#3b82f6", "#60a5fa", "#93c5fd", "#dbeafe"] // Sci-fi glowing blue
                    });
                    velocityLayer.addTo(mapInstance.current);
                })
                .catch(err => console.error("Error loading wind data:", err));
        }
        return () => {
            if (mapInstance.current) {
                mapInstance.current.remove();
                mapInstance.current = null;
            }
        };
    }, []);

    // 2. React to API Data and Bind Real Values
    useEffect(() => {
        if (!mapInstance.current || wards.length === 0) return;

        const geojsonFile = granularity === 'ward' ? '/kaggle_wards.geojson' : '/delhi_wards.geojson';
        
        fetch(geojsonFile)
            .then(res => res.json())
            .then(data => {
                if (geoJsonLayer.current) {
                    mapInstance.current!.removeLayer(geoJsonLayer.current);
                }

                geoJsonLayer.current = L.geoJSON(data, {
                    style: (feature) => {
                        const featureId = feature?.properties?.ward_no || feature?.properties?.name || feature?.properties?.ward_name;
                        const wardData = wards.find(w => w.id === String(featureId));
                        const isSelected = selectedWard && selectedWard.id === String(featureId);
                        
                        let color = '#3b82f6'; // Deep blue fallback
                        if (wardData) {
                            if (wardData.aqi > 300) color = '#ef4444'; // Red
                            else if (wardData.aqi > 200) color = '#f97316'; // Orange
                            else if (wardData.aqi > 100) color = '#f59e0b'; // Yellow
                            else color = '#10b981'; // Emerald
                        }

                        return {
                            color: color,
                            weight: isSelected ? 4 : 2,
                            fillColor: color,
                            fillOpacity: isSelected ? 0.7 : 0.35,
                            dashArray: isSelected ? '' : '4'
                        };
                    },
                    onEachFeature: (feature, layer) => {
                        const featureId = feature?.properties?.ward_no || feature?.properties?.name || feature?.properties?.ward_name;
                        const wardData = wards.find(w => w.id === String(featureId));
                        if (wardData) {
                            // Wire the Interaction Engine!
                            layer.on('click', () => {
                                onWardClick(wardData);
                                if (mapInstance.current) {
                                    // Smooth camera pan to the clicked node
                                    mapInstance.current.flyTo([wardData.lat, wardData.lon], 13, { duration: 1.0 });
                                }
                            });
                            
                            layer.bindTooltip(`
                                <div style="text-align:center; padding: 4px;">
                                    <b>${wardData.name}</b><br/>
                                    <span style="color:#64748b; font-size:10px;">AQI Level: </span>
                                    <strong style="font-size:14px; color:${wardData.aqi > 300 ? '#ef4444' : '#f97316'};">${wardData.aqi}</strong>
                                </div>
                            `, { direction: 'top', sticky: true, className: 'custom-tooltip' });
                        }
                    }
                }).addTo(mapInstance.current!);
            })
            .catch(err => console.error("Error loading ward geojson:", err));

    }, [wards, selectedWard]);

    return (
        <div
            ref={mapRef}
            style={{ height: '100%', width: '100%', position: 'absolute', top: 0, left: 0 }}
        />
    );
}
