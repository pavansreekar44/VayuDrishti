import React, { useState, useMemo } from 'react';
import LeafletMap from './components/LeafletMap';
import MapControl from './components/MapControl';

function useRealHeatmapData() {
  const [data, setData] = React.useState<any[]>([]);

  React.useEffect(() => {
    async function fetchOpenAQ() {
      try {
        // Fetch live air quality sensors in a 25km radius around Hyderabad
        const res = await fetch('https://api.openaq.org/v2/latest?coordinates=17.3850,78.4867&radius=25000&limit=100');
        const json = await res.json();

        if (json && json.results) {
          const points = json.results.map((r: any) => {
            const pm25 = r.measurements.find((m: any) => m.parameter === 'pm25')?.value || 15.0;
            // Normalize PM2.5 to a 0-1 intensity factor for Leaflet Heatmap
            const intensity = Math.min(pm25 / 150.0, 1.0);
            return [r.coordinates.latitude, r.coordinates.longitude, intensity];
          });
          setData(points);
        }
      } catch (e) {
        console.error("OpenAQ live API fetch failed:", e);
      }
    }
    fetchOpenAQ();
  }, []);

  return data;
}

function App() {
  const [healthSensitivity, setHealthSensitivity] = useState(50);
  const [isLoading, setIsLoading] = useState(false);
  const [loadingStep, setLoadingStep] = useState<string>("");
  const [routeStats, setRouteStats] = useState<any>(null);

  const [shortestRoute, setShortestRoute] = useState<any>(null);
  const [cleanestRoute, setCleanestRoute] = useState<any>(null);

  const heatmapData = useRealHeatmapData();

  const handleCompareRoutes = async (startAddress: string, endAddress: string) => {
    setIsLoading(true);
    setLoadingStep("Geocoding addresses via OpenStreetMap...");
    setRouteStats(null);
    setShortestRoute(null);
    setCleanestRoute(null);

    try {
      // 1. Geocode Start Address
      const startRes = await fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(startAddress)}`);
      const startData = await startRes.json();

      // 2. Geocode Destination Address
      const endRes = await fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(endAddress)}`);
      const endData = await endRes.json();

      if (!startData || startData.length === 0 || !endData || endData.length === 0) {
        alert("Could not find GPS coordinates for one or both addresses.");
        setLoadingStep("");
        setIsLoading(false);
        return;
      }

      const startLat = parseFloat(startData[0].lat);
      const startLon = parseFloat(startData[0].lon);
      const endLat = parseFloat(endData[0].lat);
      const endLon = parseFloat(endData[0].lon);

      // 3. Query Backend AI Routing Engine
      setLoadingStep("Solving complex A* Route (May take 30-60s in Python)...");
      const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
      const url = `${API_BASE}/api/v1/navigation/route?start_lat=${startLat}&start_lon=${startLon}&end_lat=${endLat}&end_lon=${endLon}&health_sensitivity=${healthSensitivity}`;
      const routeRes = await fetch(url);

      if (!routeRes.ok) {
        alert("API Error: Routing engine failed to find a continuous path between these points on the map.");
        setLoadingStep("");
        setIsLoading(false);
        return;
      }

      const routeData = await routeRes.json();

      // Update route statistics panel
      setRouteStats(routeData.stats);

      // Reverse GeoJSON [lon, lat] coordinates to Leaflet Polyline expected format [lat, lon]
      const shortCoords = routeData.shortest_path_geojson.features[0].geometry.coordinates.map((c: number[]) => [c[1], c[0]]);
      const cleanCoords = routeData.cleanest_path_geojson.features[0].geometry.coordinates.map((c: number[]) => [c[1], c[0]]);

      setShortestRoute(shortCoords);
      setCleanestRoute(cleanCoords);

    } catch (err) {
      console.error("Routing Error:", err);
      alert("A network error occurred while reaching the routing engine.");
    } finally {
      setLoadingStep("");
      setIsLoading(false);
    }
  };

  return (
    <div className="w-full h-screen relative bg-slate-900 overflow-hidden">

      <LeafletMap
        heatmapData={heatmapData}
        shortestRoute={shortestRoute}
        cleanestRoute={cleanestRoute}
      />

      <MapControl
        healthSensitivity={healthSensitivity}
        setHealthSensitivity={setHealthSensitivity}
        onCompareRoutes={handleCompareRoutes}
        isLoading={isLoading}
        loadingStep={loadingStep}
        routeStats={routeStats}
      />

    </div>
  );
}

export default App;
