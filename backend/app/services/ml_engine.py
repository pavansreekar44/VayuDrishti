"""
===========================================================================
 VAYU DRISHTI — ML Inference Engine (v3: 250-Node GAT+LSTM)
===========================================================================
 Uses the production VayuDrishtiModel (GAT+LSTM, no MLP) trained on 250
 nodes: 39 CPCB anchor stations + 211 ward centroids.

 Input tensor shape:  [1, 24, 250, 7]
 Features:            [U, V, PM2.5, PM10, NO2, SO2, CO]
 Output tensor shape: [1, 250, 5]
 Targets:             [PM2.5, PM10, NO2, SO2, CO]

 Key design:
   - 24h historical CPCB data from OpenAQ /measurements endpoint
   - Real wind (U,V) for ALL 250 nodes via free OpenMeteo API
   - Z-score scaling with post-scale chemical masking for nodes 39-249
   - Hourly background cron; /wards serves cached JSON instantly
===========================================================================
"""

import math
import os
import sys
import json
import time
import logging
import csv
import requests
import numpy as np
import torch
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# AQI Calculation (Indian CPCB scale)
# ---------------------------------------------------------------------------

def calculate_indian_aqi(pm25: float, pm10: float, no2: float, so2: float, co: float) -> Tuple[int, str]:
    """
    Calculates Indian CPCB AQI using 5 pollutants.
    CO is expected in mg/m³, others in µg/m³.
    """
    def get_sub_index(c, breakpoints):
        if c <= 0:
            return 0
        for c_lo, c_hi, i_lo, i_hi in breakpoints:
            if c_lo <= c <= c_hi:
                if c_lo == c_hi:
                    return i_lo
                return int(round(i_lo + (c - c_lo) * (i_hi - i_lo) / (c_hi - c_lo)))
        return 0

    bp_pm25 = [(0, 30, 0, 50), (31, 60, 51, 100), (61, 90, 101, 200), (91, 120, 201, 300), (121, 250, 301, 400), (251, 9999, 401, 500)]
    bp_pm10 = [(0, 50, 0, 50), (51, 100, 51, 100), (101, 250, 101, 200), (251, 350, 201, 300), (351, 430, 301, 400), (431, 9999, 401, 500)]
    bp_no2 = [(0, 40, 0, 50), (41, 80, 51, 100), (81, 180, 101, 200), (181, 280, 201, 300), (281, 400, 301, 400), (401, 9999, 401, 500)]
    bp_so2 = [(0, 40, 0, 50), (41, 80, 51, 100), (81, 380, 101, 200), (381, 800, 201, 300), (801, 1600, 301, 400), (1601, 9999, 401, 500)]
    bp_co = [(0, 1.0, 0, 50), (1.1, 2.0, 51, 100), (2.1, 10.0, 101, 200), (10.1, 17.0, 201, 300), (17.1, 34.0, 301, 400), (34.1, 9999.0, 401, 500)]

    c_pm25 = round(pm25)
    c_pm10 = round(pm10)
    c_no2 = round(no2)
    c_so2 = round(so2)
    c_co = round(co, 1)

    subs = {
        "PM2.5": get_sub_index(c_pm25, bp_pm25),
        "PM10": get_sub_index(c_pm10, bp_pm10),
        "NO2": get_sub_index(c_no2, bp_no2),
        "SO2": get_sub_index(c_so2, bp_so2),
        "CO": get_sub_index(c_co, bp_co)
    }

    max_val = max(subs.values())

    # Tie-breaker priority: PM2.5 > PM10 > NO2 > SO2 > CO
    dominant = "PM2.5"
    for p in ["PM2.5", "PM10", "NO2", "SO2", "CO"]:
        if subs[p] == max_val:
            dominant = p
            break

    final_aqi = min(int(max_val), 500)
    return final_aqi, dominant


def get_status(aqi: int) -> str:
    if aqi <= 50:   return "Good"
    if aqi <= 100:  return "Satisfactory"
    if aqi <= 200:  return "Moderate"
    if aqi <= 300:  return "Poor"
    if aqi <= 400:  return "Very Poor"
    return "Severe"


def detect_source(pm25: float, pm10: float, no2: float, so2: float, co: float) -> str:
    if so2 > 15 and pm10 > 100:
        return "Industrial Plume + Resuspended Road Dust"
    elif no2 > 40 and co > 1.0:
        return "Dense Traffic & Commercial Congestion"
    elif no2 > 20 and co > 0.5:
        return "Vehicular Combustion + Biomass Influence"
    else:
        return "Background Regional Transport"


# ---------------------------------------------------------------------------
# Wind conversion helper
# ---------------------------------------------------------------------------

def wind_to_uv(speed: float, direction_deg: float) -> Tuple[float, float]:
    """Convert meteorological wind speed/direction to U,V components."""
    rad = math.radians(direction_deg)
    u = -speed * math.sin(rad)
    v = -speed * math.cos(rad)
    return u, v


# ---------------------------------------------------------------------------
# Spatial Registry Loader
# ---------------------------------------------------------------------------

def load_spatial_registry(csv_path: str) -> List[dict]:
    """Load the master spatial registry CSV. Returns list of dicts ordered by node_index."""
    registry = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            node_idx = int(row['node_index'])
            ward_name = row.get('ward_name', '').strip()
            station_name = row.get('station_name', '').strip()
            is_anchor = int(row.get('is_anchor', 0))

            # Determine the display name for this node
            if is_anchor and station_name and station_name != 'None':
                display_name = station_name
            elif ward_name:
                display_name = ward_name
            elif node_idx == 86:
                display_name = "Unnamed_Ward_86"
            else:
                display_name = f"Node_{node_idx}"

            registry.append({
                'node_index': node_idx,
                'node_type': row.get('node_type', ''),
                'station_name': station_name if station_name != 'None' else '',
                'ward_name': ward_name,
                'display_name': display_name,
                'lat': float(row['latitude']),
                'lon': float(row['longitude']),
                'is_anchor': bool(is_anchor),
            })
    # Sort by node_index to guarantee order
    registry.sort(key=lambda x: x['node_index'])
    return registry


# ---------------------------------------------------------------------------
# OpenMeteo Wind Fetcher (batch for all 250 nodes)
# ---------------------------------------------------------------------------

def fetch_openmeteo_wind(registry: List[dict]) -> List[Tuple[float, float]]:
    """
    Fetch current wind speed/direction for all 250 nodes using OpenMeteo.
    Returns list of (U, V) tuples in node order.
    OpenMeteo supports batch requests with comma-separated lat/lon.
    """
    # OpenMeteo supports up to ~300 locations in a single batch call
    lats = ",".join(f"{n['lat']:.4f}" for n in registry)
    lons = ",".join(f"{n['lon']:.4f}" for n in registry)

    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lats}&longitude={lons}"
        f"&current=wind_speed_10m,wind_direction_10m"
    )

    uv_results = [(0.0, 0.0)] * len(registry)

    try:
        resp = requests.get(url, timeout=60)
        if resp.status_code != 200:
            logger.error(f"[OpenMeteo] Wind fetch failed: HTTP {resp.status_code}")
            return uv_results

        data = resp.json()
        # Single location returns a dict, multiple returns a list
        if isinstance(data, dict):
            data = [data]

        for i, item in enumerate(data):
            if i >= len(registry):
                break
            current = item.get("current", {})
            ws = current.get("wind_speed_10m", 0.0) or 0.0
            wd = current.get("wind_direction_10m", 0.0) or 0.0
            # OpenMeteo returns km/h — convert to m/s
            ws_ms = ws / 3.6
            u, v = wind_to_uv(ws_ms, wd)
            uv_results[i] = (u, v)

        logger.info(f"[OpenMeteo] Wind fetched for {len(data)} nodes successfully.")
    except Exception as e:
        logger.error(f"[OpenMeteo] Wind fetch error: {e}")

    return uv_results


# ---------------------------------------------------------------------------
# OpenAQ 24-Hour Historical Fetcher
# ---------------------------------------------------------------------------

OPENAQ_API_KEY = os.getenv(
    "OPENAQ_API_KEY",
    "a48c3556e253887d4098147a13ff033b81ccd7ac36fede20ff5c3b8eb7be4029"
)
OPENAQ_BASE_URL = "https://api.openaq.org/v3"


class OpenAQ24HFetcher:
    """
    Fetches 24 hours of historical measurements for 39 CPCB stations.
    Implements strict rate limiting: 50 calls per minute max.
    """

    def __init__(self):
        self.headers = {"X-API-Key": OPENAQ_API_KEY} if OPENAQ_API_KEY else {}
        self._call_count = 0
        self._window_start = time.time()
        self._station_id_cache: Dict[str, int] = {}
        self._sensor_map_cache: Dict[int, dict] = {}

    def _rate_limited_get(self, url: str, params: dict = None, timeout: int = 15) -> Optional[requests.Response]:
        """Make a GET request with strict 50req/min rate limiting."""
        now = time.time()
        if now - self._window_start >= 60:
            self._window_start = now
            self._call_count = 0

        if self._call_count >= 50:
            logger.warning("[OpenAQ] Rate limit approaching (50 reqs/min). Sleeping 30s...")
            time.sleep(30)
            self._window_start = time.time()
            self._call_count = 0

        try:
            resp = requests.get(url, params=params, headers=self.headers, timeout=timeout)
            self._call_count += 1

            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", 30))
                logger.warning(f"[OpenAQ] 429 Rate Limited. Sleeping {retry_after}s...")
                time.sleep(retry_after)
                self._window_start = time.time()
                self._call_count = 0
                resp = requests.get(url, params=params, headers=self.headers, timeout=timeout)
                self._call_count += 1

            return resp if resp.status_code == 200 else None
        except Exception as e:
            logger.error(f"[OpenAQ] Request error: {e}")
            return None

    def discover_station_ids(self, station_coords: Dict[str, Tuple[float, float]]) -> Dict[str, int]:
        """Find OpenAQ location IDs using exact name match, fallback to 3km radial search."""
        if self._station_id_cache:
            return self._station_id_cache

        logger.info(f"[OpenAQ] Discovering IDs for {len(station_coords)} stations (Primary: Exact, Fallback: 3km)...")
        for name, (lat, lon) in station_coords.items():
            best = None
            
            # 1. Primary Fetch (Exact String Match)
            resp = self._rate_limited_get(
                f"{OPENAQ_BASE_URL}/locations",
                params={"name": name, "isMonitor": "true", "limit": 100}
            )
            if resp and resp.status_code == 200:
                results = resp.json().get("results", [])
                for loc in results:
                    if loc.get("name") == name:
                        best = loc
                        break

            # 2. Fallback Fetch (3km Radial)
            if not best:
                logger.info(f"[OpenAQ] Primary fetch failed for {name}. Falling back to 3km radial search...")
                resp = self._rate_limited_get(
                    f"{OPENAQ_BASE_URL}/locations",
                    params={"coordinates": f"{lat},{lon}", "radius": 3000, "isMonitor": "true", "limit": 5}
                )
                if resp and resp.status_code == 200:
                    results = resp.json().get("results", [])
                    if results:
                        # Pick freshest location
                        best_time = None
                        for loc in results:
                            dt_obj = loc.get("datetimeLast")
                            if dt_obj and isinstance(dt_obj, dict):
                                dt_str = dt_obj.get("utc")
                                if dt_str:
                                    try:
                                        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                                        if best_time is None or dt > best_time:
                                            best_time = dt
                                            best = loc
                                    except (ValueError, TypeError):
                                        pass
                        if best is None:
                            best = results[0]  # default if no date parsed

            if not best:
                logger.warning(f"[OpenAQ] No reference-grade location found for {name}")
                continue

            self._station_id_cache[name] = best["id"]
            
            # Cache sensor metadata
            sensors = best.get("sensors", [])
            s_map = {}
            for s in sensors:
                sid = s.get("id")
                pname = s.get("parameter", {}).get("name", "").lower()
                unit = s.get("parameter", {}).get("units", "")
                if sid:
                    s_map[sid] = (pname, unit)
            self._sensor_map_cache[best["id"]] = s_map
            
            logger.info(f"[OpenAQ] {name} → ID {best['id']}")

        logger.info(f"[OpenAQ] Discovered {len(self._station_id_cache)}/{len(station_coords)} stations.")
        return self._station_id_cache

    def fetch_24h_measurements(self, location_id: int, station_name: str) -> Dict[int, dict]:
        hourly = {h: {'pm25': None, 'pm10': None, 'no2': None, 'so2': None, 'co': None, 'ws': None, 'wd': None} for h in range(24)}
        
        # Use /latest and replicate across 24h
        resp = self._rate_limited_get(f"{OPENAQ_BASE_URL}/locations/{location_id}/latest")
        if not resp:
            # If missing, fill with 0.0
            for h in range(24):
                for k in hourly[h]: hourly[h][k] = 0.0
            return hourly
        
        results = resp.json().get("results", [])
        sensor_map = self._sensor_map_cache.get(location_id, {})
        
        PARAM_MAP = {
            'pm25': 'pm25', 'pm2.5': 'pm25', 'pm10': 'pm10',
            'no2': 'no2', 'so2': 'so2', 'co': 'co', 'carbon_monoxide': 'co'
        }
        
        latest_vals = {}
        for r in results:
            sid = r.get("sensorsId")
            val = r.get("value")
            if sid not in sensor_map or val is None: continue
            
            pname, unit = sensor_map[sid]
            mapped = PARAM_MAP.get(pname)
            if not mapped: continue
            
            # Unit conversions
            if mapped == 'no2' and unit == 'ppb': val *= 1.88
            elif mapped == 'so2' and unit == 'ppb': val *= 2.62
            elif mapped == 'co':
                if unit == 'µg/m³': val /= 1000.0
                elif unit == 'ppm': val *= 1.15
            elif unit not in ["µg/m³", "mg/m³"]:
                continue
                
            latest_vals[mapped] = val
            
        # Replicate across 24 hours
        for h in range(24):
            for param in PARAM_MAP.values():
                if param in latest_vals:
                    hourly[h][param] = latest_vals[param]
                
        # Fill remaining with 0.0
        for h in range(24):
            for k in hourly[h]:
                if hourly[h][k] is None:
                    hourly[h][k] = 0.0
                    
        return hourly


# ---------------------------------------------------------------------------
# Main ML Engine
# ---------------------------------------------------------------------------

class VayuDrishtiEngine:
    """
    Production ML inference engine for the 250-node VayuDrishti GAT+LSTM model.
    Runs hourly, caches results, serves /wards endpoint instantly.
    """

    def __init__(self):
        logger.info("[ML Engine] Booting VayuDrishti 250-Node GAT+LSTM Engine...")
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.model = None
        self.edge_index = None
        self.scaler_means = None
        self.scaler_stds = None
        self.registry: List[dict] = []
        self.use_torch = False

        # In-memory prediction cache
        self.prediction_cache: Dict[str, dict] = {}
        self.cache_timestamp: float = 0.0
        self.cache_error: Optional[str] = None

        base_dir = os.path.join(os.path.dirname(__file__), "vayu_model")

        try:
            # 1. Load spatial registry
            csv_path = os.path.join(base_dir, "master_spatial_registry.csv")
            self.registry = load_spatial_registry(csv_path)
            logger.info(f"[ML Engine] Loaded spatial registry: {len(self.registry)} nodes.")

            # 2. Load model architecture
            sys.path.insert(0, base_dir)
            from model import VayuDrishtiModel

            weights_path = os.path.join(base_dir, "vayu_drishti_final.pth")
            self.model = VayuDrishtiModel(in_features=7, hidden_dim=64, out_features=5, heads=4)
            self.model.load_state_dict(
                torch.load(weights_path, map_location=self.device, weights_only=True)
            )
            self.model.to(self.device)
            self.model.eval()
            logger.info(f"[ML Engine] Model loaded on {self.device.type.upper()}")

            # 3. Load edge index
            ei_path = os.path.join(base_dir, "delhi_250_8km_edge_index.pt")
            self.edge_index = torch.load(ei_path, map_location=self.device, weights_only=True)
            if isinstance(self.edge_index, dict):
                self.edge_index = self.edge_index.get("edge_index", self.edge_index)
            self.edge_index = self.edge_index.to(self.device)
            logger.info(f"[ML Engine] Edge index loaded: {self.edge_index.shape}")

            # 4. Load Z-score scaler
            scaler_path = os.path.join(base_dir, "vayu_scaler.json")
            with open(scaler_path, 'r') as f:
                scaler_data = json.load(f)
            self.scaler_means = np.array(scaler_data["means"], dtype=np.float32)  # [7]
            self.scaler_stds = np.array(scaler_data["stds"], dtype=np.float32)    # [7]
            logger.info(f"[ML Engine] Scaler loaded. Features: {scaler_data['features']}")

            self.use_torch = True
            logger.info("[ML Engine] ✓ All components loaded successfully.")

        except Exception as e:
            logger.error(f"[ML Engine] FATAL initialization error: {e}")
            import traceback
            traceback.print_exc()

        # OpenAQ fetcher
        self.openaq = OpenAQ24HFetcher()

    def run_inference_cycle(self):
        """
        Full inference pipeline. Called once per hour by the background task.
        1) Fetch OpenAQ 24h data for 39 stations
        2) Fetch OpenMeteo wind for all 250 nodes
        3) Build [1, 24, 250, 7] tensor
        4) Z-score scale + chemical mask
        5) Forward pass
        6) Inverse-scale outputs
        7) Build named JSON response and cache it
        """
        if not self.use_torch:
            self.cache_error = "ML model not loaded"
            logger.error("[ML Engine] Cannot run inference — model not loaded.")
            return

        logger.info("[ML Engine] === Starting Hourly Inference Cycle ===")
        cycle_start = time.time()

        try:
            # Import station coords
            from app.core.stations import STATION_COORDS

            # ── Step 1: Discover OpenAQ station IDs ──
            self.openaq.discover_station_ids(STATION_COORDS)

            # ── Step 2: Fetch 24h historical data for 39 CPCB stations ──
            logger.info("[ML Engine] Fetching 24h historical data from OpenAQ...")
            station_24h: Dict[str, Dict[int, dict]] = {}

            for stn_name in STATION_COORDS:
                loc_id = self.openaq._station_id_cache.get(stn_name)
                if loc_id is None:
                    logger.warning(f"[ML Engine] No OpenAQ ID for {stn_name}, masking with 0.0")
                    station_24h[stn_name] = {h: {'pm25': 0.0, 'pm10': 0.0, 'no2': 0.0, 'so2': 0.0, 'co': 0.0, 'ws': 0.0, 'wd': 0.0} for h in range(24)}
                    continue
                station_24h[stn_name] = self.openaq.fetch_24h_measurements(loc_id, stn_name)

            logger.info(f"[ML Engine] OpenAQ data fetched for {len(station_24h)} stations.")

            # ── Step 3: Fetch OpenMeteo wind for all 250 nodes ──
            logger.info("[ML Engine] Fetching OpenMeteo wind for 250 nodes...")
            wind_uv = fetch_openmeteo_wind(self.registry)

            # ── Step 4: Build raw tensor [1, 24, 250, 7] ──
            # Features: [U, V, PM2.5, PM10, NO2, SO2, CO]
            raw_tensor = np.zeros((1, 24, 250, 7), dtype=np.float32)

            # Map station names to node indices
            stn_name_to_idx = {}
            for node in self.registry:
                if node['is_anchor'] and node['station_name']:
                    stn_name_to_idx[node['station_name']] = node['node_index']

            # Fill CPCB station data (nodes 0-38)
            for stn_name, hourly_data in station_24h.items():
                idx = stn_name_to_idx.get(stn_name)
                if idx is None:
                    continue
                for h in range(24):
                    hd = hourly_data.get(h, {})
                    ws = hd.get('ws', 0.0) or 0.0
                    wd = hd.get('wd', 0.0) or 0.0
                    u, v = wind_to_uv(ws, wd)
                    raw_tensor[0, h, idx, 0] = u
                    raw_tensor[0, h, idx, 1] = v
                    raw_tensor[0, h, idx, 2] = hd.get('pm25', 0.0) or 0.0
                    raw_tensor[0, h, idx, 3] = hd.get('pm10', 0.0) or 0.0
                    raw_tensor[0, h, idx, 4] = hd.get('no2', 0.0) or 0.0
                    raw_tensor[0, h, idx, 5] = hd.get('so2', 0.0) or 0.0
                    raw_tensor[0, h, idx, 6] = (hd.get('co', 0.0) or 0.0) / 1000.0  # OpenAQ µg/m³ to mg/m³

            # Fill wind U,V from OpenMeteo for ALL 250 nodes (replicated across 24h)
            # This overwrites wind for CPCB nodes too with current-snapshot wind.
            # For nodes 39-249, this is the ONLY non-zero data they get.
            for i, (u, v) in enumerate(wind_uv):
                for h in range(24):
                    raw_tensor[0, h, i, 0] = u
                    raw_tensor[0, h, i, 1] = v

            # ── Step 5: Z-score scale the ENTIRE tensor ──
            scaled_tensor = (raw_tensor - self.scaler_means) / self.scaler_stds

            # ── Step 6: Post-scale chemical mask ──
            # 1. Deserted nodes (39-249) have no chemical sensors, force them to 0.0 mask token
            scaled_tensor[:, :, 39:, 2:] = 0.0
            
            # 2. Anchor stations (0-38) with missing data (raw == 0.0) must ALSO be forced to 0.0 mask token.
            # If we don't do this, raw 0.0 becomes (0 - mean)/std = ~ -2.0, which the model interprets as perfectly clean air!
            missing_chem_mask = (raw_tensor[:, :, :39, 2:] == 0.0)
            scaled_tensor[:, :, :39, 2:][missing_chem_mask] = 0.0

            # ── Step 7: Forward pass ──
            x_tensor = torch.tensor(scaled_tensor, dtype=torch.float32).to(self.device)

            with torch.no_grad():
                predictions = self.model(x_tensor, self.edge_index)
                # predictions shape: [1, 250, 5]

            pred_np = predictions[0].cpu().numpy()  # [250, 5]

            # ── Step 8: Inverse Z-score the 5 output features ──
            # Output features correspond to indices 2-6 of the scaler (PM2.5, PM10, NO2, SO2, CO)
            output_means = self.scaler_means[2:]  # [5]
            output_stds = self.scaler_stds[2:]    # [5]
            pred_unscaled = pred_np * output_stds + output_means

            # ── Step 9: Build named JSON response ──
            result_cache = {}
            for i, node in enumerate(self.registry):
                pm25_val = max(0.0, float(pred_unscaled[i, 0]))
                pm10_val = max(0.0, float(pred_unscaled[i, 1]))
                no2_val = max(0.0, float(pred_unscaled[i, 2]))
                so2_val = max(0.0, float(pred_unscaled[i, 3]))
                co_val = max(0.0, float(pred_unscaled[i, 4]))

                pm25_clamped = min(500.0, pm25_val)
                aqi, dom_pol = calculate_indian_aqi(pm25_clamped, pm10_val, no2_val, so2_val, co_val)

                key = node['display_name']
                result_cache[key] = {
                    "name": key,
                    "lat": node['lat'],
                    "lon": node['lon'],
                    "aqi": aqi,
                    "dominant_pollutant": dom_pol,
                    "pm25": round(pm25_clamped, 1),
                    "pm10": round(pm10_val, 1),
                    "no2": round(no2_val, 1),
                    "so2": round(so2_val, 1),
                    "co": round(co_val, 3),
                    "dominant_source": detect_source(pm25_clamped, pm10_val, no2_val, so2_val, co_val),
                    "status": get_status(aqi),
                    "trend": "stable",
                    "is_station": node['is_anchor'],
                    "node_type": node['node_type'],
                }

            self.prediction_cache = result_cache
            self.cache_timestamp = time.time()
            self.cache_error = None

            elapsed = int(time.time() - cycle_start)
            logger.info(f"[ML Engine] === Inference Cycle Complete: {len(result_cache)} predictions in {elapsed}s ===")

        except Exception as e:
            self.cache_error = f"Inference cycle failed: {e}"
            logger.error(f"[ML Engine] FATAL inference error: {e}")
            import traceback
            traceback.print_exc()

    def get_cached_predictions(self) -> Tuple[Dict[str, dict], float, Optional[str]]:
        """Return the cached prediction dict, timestamp, and any error."""
        return self.prediction_cache, self.cache_timestamp, self.cache_error


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
ML_ENGINE = VayuDrishtiEngine()
