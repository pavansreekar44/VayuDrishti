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
    disableWind?: boolean;
    layer?: 'aqi' | 'pm25' | 'sources';
}

// 8 wards dropped from the ML graph — render as neutral null zones
const DROPPED_WARDS = new Set([
    'CHANDANI MAHAL',
    'ROHINI-B',
    'RANI KHERA',
    'CIVIL LINES',
    'RAJOURI GARDEN',
    'NILOTHI',
    'JAMA MASJID',
    'CHAUKHANDI NAGAR',
]);

// 5 CPCB stations that have no GeoJSON polygon — render as point markers
const POINT_MARKER_STATIONS = [
    'Cantonment Area',
    'Lodhi Road',
    'Major Dhyan Chand National Stadium',
    'Mandir Marg',
    'Talkatora Garden',
];

// Inject custom tooltip CSS once at module load
if (typeof document !== 'undefined' && !document.getElementById('vayu-tooltip-style')) {
    const style = document.createElement('style');
    style.id = 'vayu-tooltip-style';
    style.textContent = `
        .vayu-tooltip {
            background: rgba(10, 14, 26, 0.92) !important;
            border: 1px solid rgba(99, 179, 237, 0.35) !important;
            border-radius: 8px !important;
            padding: 8px 12px !important;
            box-shadow: 0 4px 20px rgba(0,0,0,0.55) !important;
            font-family: 'Inter', system-ui, sans-serif !important;
            color: #e2e8f0 !important;
            pointer-events: none !important;
            backdrop-filter: blur(8px);
        }
        .vayu-tooltip::before { display: none !important; }
        .leaflet-tooltip.vayu-tooltip { background: rgba(10,14,26,0.92); }
    `;
    document.head.appendChild(style);
}

function getAqiColor(aqi: number): string {
    if (aqi > 400) return '#7f1d1d'; // Severe - dark red
    if (aqi > 300) return '#ef4444'; // Very Poor - red
    if (aqi > 200) return '#f97316'; // Poor - orange
    if (aqi > 100) return '#f59e0b'; // Moderate - yellow
    if (aqi > 50)  return '#84cc16'; // Satisfactory - lime
    return '#10b981'; // Good - emerald
}

function getPm25Color(pm25: number): string {
    if (pm25 > 250) return '#dc2626';
    if (pm25 > 150) return '#f97316';
    if (pm25 > 75)  return '#fbbf24';
    return '#22c55e';
}

function getSourceColor(source: string): string {
    if (source.includes('Traffic') || source.includes('Congestion')) return '#ef4444';
    if (source.includes('Industrial')) return '#f59e0b';
    if (source.includes('Construction') || source.includes('Dust')) return '#8b5cf6';
    if (source.includes('Biomass')) return '#f97316';
    return '#64748b';
}

export default function LeafletMap({ wards, selectedWard, onWardClick, granularity, disableWind = false, layer = 'aqi' }: LeafletMapProps) {
    const mapRef = useRef<HTMLDivElement>(null);
    const mapInstance = useRef<L.Map | null>(null);
    const geoJsonLayer = useRef<L.GeoJSON | null>(null);
    const markersLayer = useRef<L.LayerGroup | null>(null);

    // 1. Initialize Map once
    useEffect(() => {
        if (!mapRef.current) return;
        if (!mapInstance.current) {
            mapInstance.current = L.map(mapRef.current, { zoomControl: false }).setView([28.6139, 77.2090], 11);
            L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
                attribution: '&copy; OpenStreetMap contributors'
            }).addTo(mapInstance.current);
            L.control.zoom({ position: 'bottomright' }).addTo(mapInstance.current);
        }
        return () => {
            if (mapInstance.current) {
                mapInstance.current.remove();
                mapInstance.current = null;
            }
        };
    }, []);

    // 2. React to API Data and Bind Real Values with Layer Support
    useEffect(() => {
        if (!mapInstance.current || wards.length === 0) return;

        // Build a lookup: ward name (uppercase) -> ward data
        const wardLookup = new Map<string, any>();
        for (const w of wards) {
            if (w.name) {
                wardLookup.set(w.name.toUpperCase(), w);
            }
        }

        const geojsonFile = granularity === 'ward' ? '/kaggle_wards.geojson' : '/delhi_wards.geojson';

        fetch(geojsonFile)
            .then(res => res.json())
            .then(data => {
                // Remove previous layers
                if (geoJsonLayer.current) {
                    mapInstance.current!.removeLayer(geoJsonLayer.current);
                }
                if (markersLayer.current) {
                    mapInstance.current!.removeLayer(markersLayer.current);
                }

                geoJsonLayer.current = L.geoJSON(data, {
                    style: (feature) => {
                        const wardName = (
                            feature?.properties?.WardName ||
                            feature?.properties?.ward_name ||
                            feature?.properties?.name ||
                            ''
                        ).toUpperCase().trim();

                        const isSelected = selectedWard && selectedWard.name.toUpperCase() === wardName;

                        // Rule 3: Dropped wards — neutral null zone
                        if (DROPPED_WARDS.has(wardName)) {
                            return {
                                color: '#94a3b8',
                                weight: 1,
                                fillColor: '#cbd5e1', // slate-300
                                fillOpacity: 0.3,
                                dashArray: '6',
                            };
                        }

                        // Rule 1: MCD Polygons — match by name
                        const wardData = wardLookup.get(wardName);

                        let color = '#3b82f6'; // fallback blue
                        if (wardData) {
                            if (layer === 'aqi') {
                                color = getAqiColor(wardData.aqi);
                            } else if (layer === 'pm25') {
                                color = getPm25Color(wardData.pm25 || 0);
                            } else if (layer === 'sources') {
                                color = getSourceColor(wardData.dominant_source || '');
                            }
                        }

                        return {
                            color: color,
                            weight: isSelected ? 4 : 2,
                            fillColor: color,
                            fillOpacity: isSelected ? 0.7 : 0.35,
                            dashArray: isSelected ? '' : '4'
                        };
                    },
                    onEachFeature: (feature, layer_obj) => {
                        const wardName = (
                            feature?.properties?.WardName ||
                            feature?.properties?.ward_name ||
                            feature?.properties?.name ||
                            ''
                        ).toUpperCase().trim();

                        const displayName = feature?.properties?.WardName ||
                            feature?.properties?.ward_name ||
                            feature?.properties?.name ||
                            'Unknown';

                        // Rule 3: Dropped wards — tooltip "Outside AI Processing Zone"
                        if (DROPPED_WARDS.has(wardName)) {
                            layer_obj.bindTooltip(
                                `<div style="text-align:center; min-width:120px;">
                                    <div style="font-size:13px; font-weight:700; color:#e2e8f0; margin-bottom:4px;">${displayName}</div>
                                    <div style="font-size:11px; color:#94a3b8; font-style:italic;">Outside AI Processing Zone</div>
                                </div>`,
                                { direction: 'top', sticky: true, className: 'vayu-tooltip', opacity: 1 }
                            );
                            return;
                        }

                        const wardData = wardLookup.get(wardName);

                        // Hover highlight
                        layer_obj.on('mouseover', function (this: L.Path) {
                            this.setStyle({ fillOpacity: 0.75, weight: 3 });
                        });
                        layer_obj.on('mouseout', function (this: L.Path) {
                            if (geoJsonLayer.current) geoJsonLayer.current.resetStyle(this);
                        });

                        if (wardData) {
                            layer_obj.on('click', () => {
                                onWardClick(wardData);
                                if (mapInstance.current) {
                                    mapInstance.current.flyTo([wardData.lat, wardData.lon], 13, { duration: 1.0 });
                                }
                            });
                        }

                        // Tooltip
                        const aqiColor = !wardData ? '#94a3b8'
                            : wardData.aqi > 300 ? '#ef4444'
                            : wardData.aqi > 200 ? '#f97316'
                            : wardData.aqi > 100 ? '#fbbf24'
                            : '#10b981';

                        const aqiLabel = !wardData ? 'Loading…'
                            : layer === 'aqi'   ? `AQI: <strong style="font-size:16px; color:${aqiColor};">${wardData.aqi}</strong>`
                            : layer === 'pm25'  ? `PM2.5: <strong style="font-size:14px; color:#63b3ed;">${wardData.pm25} µg/m³</strong>`
                            : `Source: <strong style="font-size:12px; color:#a78bfa;">${wardData.dominant_source}</strong>`;

                        const statusLabel = wardData?.status
                            ? `<br/><span style="color:${aqiColor}; font-size:10px; font-weight:600; letter-spacing:0.05em;">${wardData.status.toUpperCase()}</span>`
                            : '';

                        const chemLabel = wardData
                            ? `<div style="margin-top:4px; font-size:10px; color:#94a3b8;">
                                PM10: ${wardData.pm10 ?? '-'} · NO₂: ${wardData.no2 ?? '-'} · SO₂: ${wardData.so2 ?? '-'} · CO: ${wardData.co ?? '-'}
                               </div>`
                            : '';

                        const tooltipContent = `
                            <div style="text-align:center; min-width:140px;">
                                <div style="font-size:13px; font-weight:700; color:#e2e8f0; margin-bottom:4px;">${displayName}</div>
                                <div style="font-size:12px; color:#94a3b8;">${aqiLabel}</div>
                                ${statusLabel}
                                ${chemLabel}
                            </div>`;

                        layer_obj.bindTooltip(tooltipContent, {
                            direction: 'top',
                            sticky: true,
                            className: 'vayu-tooltip',
                            opacity: 1
                        });
                    }
                }).addTo(mapInstance.current!);

                // ── Rule 2: Point Markers for 5 stations without polygons ──
                markersLayer.current = L.layerGroup();

                for (const stationName of POINT_MARKER_STATIONS) {
                    const stationData = wardLookup.get(stationName.toUpperCase());
                    if (!stationData) continue;

                    const color = layer === 'aqi' ? getAqiColor(stationData.aqi)
                        : layer === 'pm25' ? getPm25Color(stationData.pm25 || 0)
                        : getSourceColor(stationData.dominant_source || '');

                    const marker = L.circleMarker([stationData.lat, stationData.lon], {
                        radius: 8,
                        color: '#ffffff',
                        weight: 2,
                        fillColor: color,
                        fillOpacity: 0.85,
                    });

                    const aqiLabel = layer === 'aqi'
                        ? `AQI: <strong style="font-size:16px; color:${color};">${stationData.aqi}</strong>`
                        : layer === 'pm25'
                        ? `PM2.5: <strong style="font-size:14px; color:#63b3ed;">${stationData.pm25} µg/m³</strong>`
                        : `Source: <strong style="font-size:12px; color:#a78bfa;">${stationData.dominant_source}</strong>`;

                    marker.bindTooltip(
                        `<div style="text-align:center; min-width:140px;">
                            <div style="font-size:13px; font-weight:700; color:#e2e8f0; margin-bottom:2px;">${stationData.name}</div>
                            <div style="font-size:10px; color:#60a5fa; margin-bottom:4px;">CPCB Station (No Polygon)</div>
                            <div style="font-size:12px; color:#94a3b8;">${aqiLabel}</div>
                            <span style="color:${color}; font-size:10px; font-weight:600;">${(stationData.status || '').toUpperCase()}</span>
                            <div style="margin-top:4px; font-size:10px; color:#94a3b8;">
                                PM10: ${stationData.pm10 ?? '-'} · NO₂: ${stationData.no2 ?? '-'} · SO₂: ${stationData.so2 ?? '-'} · CO: ${stationData.co ?? '-'}
                            </div>
                        </div>`,
                        { direction: 'top', sticky: true, className: 'vayu-tooltip', opacity: 1 }
                    );

                    marker.on('click', () => {
                        onWardClick(stationData);
                        if (mapInstance.current) {
                            mapInstance.current.flyTo([stationData.lat, stationData.lon], 14, { duration: 1.0 });
                        }
                    });

                    marker.addTo(markersLayer.current!);
                }

                markersLayer.current.addTo(mapInstance.current!);
            })
            .catch(err => console.error("Error loading ward geojson:", err));

    }, [wards, selectedWard, layer]);

    return (
        <div
            ref={mapRef}
            style={{ height: '100%', width: '100%' }}
        />
    );
}
