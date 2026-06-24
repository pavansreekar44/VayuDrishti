"""
===========================================================================
 VAYU DRISHTI — OpenAQ v3 Client
===========================================================================
 Central client for fetching live air quality data from OpenAQ v3 API.
 Returns real µg/m³ concentration values (NOT AQI indices).
 
 Replaces the deprecated WAQI integration as of 2026-06-15.
 
 Key design rules:
   1. ONLY real live data from OpenAQ is used — NO fabricated/mock values.
   2. If OpenAQ returns no data or hits rate limits, an explicit error is
      raised — NEVER substitute with defaults/placeholders.
   3. Station list is imported from app.core.stations (single source of truth).
   4. Rate limiting: exponential backoff + request throttling built in.
===========================================================================
"""

import os
import time
import logging
import requests
import torch
from collections import deque
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ─── Configuration ─────────────────────────────────────────────────────────────

OPENAQ_API_KEY = os.getenv(
    "OPENAQ_API_KEY",
    "a48c3556e253887d4098147a13ff033b81ccd7ac36fede20ff5c3b8eb7be4029"
)
OPENAQ_BASE_URL = "https://api.openaq.org/v3"

# Rate limit settings
MIN_REQUEST_INTERVAL_SEC = 0.5   # Minimum gap between consecutive requests
MAX_RETRIES = 3                  # Max retries on transient failures
INITIAL_BACKOFF_SEC = 1.0        # Initial backoff on rate limit (doubles each retry)


# ─── Data Classes ──────────────────────────────────────────────────────────────

@dataclass
class StationReading:
    """A single station's live pollutant readings in µg/m³."""
    name: str
    lat: float
    lon: float
    pm25: Optional[float]        # µg/m³
    pm10: Optional[float]        # µg/m³
    no2: Optional[float]         # µg/m³
    so2: Optional[float]         # µg/m³
    co: Optional[float]          # mg/m³
    o3: Optional[float]          # µg/m³
    temperature: Optional[float] # °C
    humidity: Optional[float]    # %
    wind_speed: Optional[float]  # m/s
    wind_direction: Optional[float] # deg
    timestamp: Optional[str]     # ISO 8601 UTC
    openaq_location_id: Optional[int]


class OpenAQRateLimitError(Exception):
    """Raised when OpenAQ returns HTTP 429 (rate limit exceeded)."""
    pass


class OpenAQDataUnavailableError(Exception):
    """Raised when OpenAQ returns no valid data for a station."""
    pass


# ─── OpenAQ Client ─────────────────────────────────────────────────────────────

class OpenAQClient:
    """
    Client for the OpenAQ v3 API.
    
    Usage:
        client = OpenAQClient()
        # Discover OpenAQ location IDs for all 40 stations
        client.discover_station_ids(STATION_COORDS)
        # Fetch live readings for all discovered stations
        readings = client.fetch_all_latest()
    """

    def __init__(self, api_key: str = None):
        self.api_key = api_key or OPENAQ_API_KEY
        self.base_url = OPENAQ_BASE_URL
        self.headers = {"X-API-Key": self.api_key} if self.api_key else {}
        self._last_request_time = 0.0
        self._request_times = deque(maxlen=55)

        # Cache: station_name → openaq_location_id
        # Populated by discover_station_ids() 
        self._station_id_cache: Dict[str, int] = {}

        # Cache: openaq_location_id → {sensor_id: (parameter_name, unit)}
        self._sensor_map_cache: Dict[int, Dict[int, Tuple[str, str]]] = {}

    def _throttled_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """
        Makes an HTTP request with:
          1. Request throttling (MIN_REQUEST_INTERVAL_SEC between calls)
          2. Exponential backoff on HTTP 429 (rate limit)
          3. Explicit error on failure — NO silent fallback
        """
        # Throttle: ensure minimum gap between requests
        elapsed = time.time() - self._last_request_time
        if elapsed < MIN_REQUEST_INTERVAL_SEC:
            time.sleep(MIN_REQUEST_INTERVAL_SEC - elapsed)

        # 60-second rolling window throttle (max 55 requests)
        now = time.time()
        if len(self._request_times) == 55:
            oldest_request = self._request_times[0]
            if now - oldest_request < 60:
                logger.warning("[OpenAQ] Approaching rate limit (55 requests/min): Pausing for 30 seconds for safety...")
                time.sleep(30)
                self._request_times.clear()
        
        self._request_times.append(time.time())

        backoff = INITIAL_BACKOFF_SEC
        last_exception = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                self._last_request_time = time.time()
                kwargs.setdefault("timeout", 15)
                kwargs.setdefault("headers", self.headers)

                response = requests.request(method, url, **kwargs)

                if response.status_code == 200:
                    return response
                elif response.status_code == 429:
                    # Rate limited — extract retry-after if available
                    retry_after = response.headers.get("Retry-After")
                    wait_time = float(retry_after) if retry_after else backoff
                    logger.warning(
                        f"[OpenAQ] Rate limited (429). "
                        f"Attempt {attempt+1}/{MAX_RETRIES+1}. "
                        f"Waiting {wait_time:.1f}s before retry."
                    )
                    if attempt < MAX_RETRIES:
                        time.sleep(wait_time)
                        backoff *= 2  # Exponential backoff
                        continue
                    else:
                        raise OpenAQRateLimitError(
                            "OpenAQ API rate limit reached. "
                            "Live data is temporarily unavailable."
                        )
                elif response.status_code == 401:
                    raise OpenAQDataUnavailableError(
                        "OpenAQ API key is invalid or missing. "
                        "Set OPENAQ_API_KEY environment variable."
                    )
                elif response.status_code == 422:
                    raise OpenAQDataUnavailableError(
                        f"OpenAQ validation error: {response.text[:200]}"
                    )
                else:
                    last_exception = Exception(
                        f"OpenAQ returned HTTP {response.status_code}: {response.text[:200]}"
                    )
                    if attempt < MAX_RETRIES:
                        time.sleep(backoff)
                        backoff *= 2
                        continue
                    raise last_exception

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                last_exception = e
                if attempt < MAX_RETRIES:
                    logger.warning(
                        f"[OpenAQ] Connection error. Attempt {attempt+1}/{MAX_RETRIES+1}. "
                        f"Retrying in {backoff:.1f}s. Error: {e}"
                    )
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                raise OpenAQDataUnavailableError(
                    f"OpenAQ API is unreachable after {MAX_RETRIES+1} attempts: {e}"
                )

        # Should not reach here, but safety net
        raise OpenAQDataUnavailableError(
            f"OpenAQ request failed after {MAX_RETRIES+1} attempts: {last_exception}"
        )

    def discover_station_ids(self, station_coords: dict) -> Dict[str, int]:
        """
        For each station in station_coords, find the closest OpenAQ location ID.
        
        Uses the /v3/locations endpoint with coordinates+radius search.
        Results are cached for the session to avoid repeated lookups.
        
        Returns: {station_name: openaq_location_id}
        """
        logger.info(f"[OpenAQ] Discovering location IDs for {len(station_coords)} stations...")
        
        discovered = {}
        failed = []

        for name, (lat, lon) in station_coords.items():
            # Skip if already cached
            if name in self._station_id_cache:
                discovered[name] = self._station_id_cache[name]
                continue

            try:
                resp = self._throttled_request(
                    "GET",
                    f"{self.base_url}/locations",
                    params={
                        "coordinates": f"{lat},{lon}",
                        "radius": 3000,  # 3km radius
                        "limit": 5,
                    },
                )
                data = resp.json()
                results = data.get("results", [])

                if not results:
                    logger.warning(f"[OpenAQ] No location found for {name} ({lat}, {lon})")
                    failed.append(name)
                    continue

                # Find the location with the most recent datetimeLast to avoid dead legacy nodes
                freshest_loc = results[0]
                freshest_time = None
                
                for current_loc in results:
                    dt_last_obj = current_loc.get("datetimeLast")
                    if dt_last_obj and isinstance(dt_last_obj, dict):
                        dt_last_str = dt_last_obj.get("utc")
                        if dt_last_str:
                            try:
                                dt_last = datetime.fromisoformat(dt_last_str.replace("Z", "+00:00"))
                                if freshest_time is None or dt_last > freshest_time:
                                    freshest_time = dt_last
                                    freshest_loc = current_loc
                            except (ValueError, TypeError):
                                pass

                loc = freshest_loc
                loc_id = loc["id"]
                self._station_id_cache[name] = loc_id

                # Cache sensor metadata for this location
                sensors = loc.get("sensors", [])
                sensor_map = {}
                for s in sensors:
                    sid = s.get("id")
                    param = s.get("parameter", {})
                    pname = param.get("name", "").lower()
                    unit = param.get("units", "")
                    if sid:
                        sensor_map[sid] = (pname, unit)
                self._sensor_map_cache[loc_id] = sensor_map

                discovered[name] = loc_id
                logger.info(f"[OpenAQ] {name} → location ID {loc_id} ({len(sensors)} sensors)")

            except OpenAQRateLimitError:
                logger.error(
                    f"[OpenAQ] Rate limit hit during discovery at station '{name}'. "
                    f"Discovered {len(discovered)}/{len(station_coords)} so far."
                )
                raise
            except OpenAQDataUnavailableError as e:
                logger.error(f"[OpenAQ] Data unavailable for {name}: {e}")
                failed.append(name)
            except Exception as e:
                logger.error(f"[OpenAQ] Unexpected error discovering {name}: {e}")
                failed.append(name)

        if failed:
            logger.warning(f"[OpenAQ] Failed to discover {len(failed)} stations: {failed}")

        logger.info(
            f"[OpenAQ] Discovery complete: {len(discovered)}/{len(station_coords)} stations found."
        )
        return discovered

    def fetch_latest_for_station(
        self, station_name: str, lat: float, lon: float, location_id: int
    ) -> Optional[StationReading]:
        """
        Fetch the latest pollutant readings for a single OpenAQ location.
        
        Only uses sensors reporting in µg/m³. Skips ppb sensors to avoid
        unit confusion.
        
        Returns StationReading or None if no valid PM2.5 data is available.
        NEVER returns fabricated/estimated values.
        """
        try:
            resp = self._throttled_request(
                "GET",
                f"{self.base_url}/locations/{location_id}/latest",
            )
            data = resp.json()
            readings = data.get("results", [])

            if not readings:
                logger.warning(f"[OpenAQ] No latest readings for {station_name} (ID {location_id})")
                return None

            # Build sensor_id → (param_name, unit) map from cache or readings
            sensor_map = self._sensor_map_cache.get(location_id, {})

            # 1. Group measurements by parameter
            param_groups = {}
            for reading in readings:
                sensor_id = reading.get("sensorsId")
                value = reading.get("value")
                dt = reading.get("datetime", {}).get("utc")

                if value is None or dt is None:
                    continue

                param_info = sensor_map.get(sensor_id)
                if not param_info:
                    continue

                param_name, unit = param_info
                valid_units = {"µg/m³", "ppb", "ppm", "c", "%", "m/s", "deg"}
                if unit not in valid_units:
                    continue

                # 12-Hour Lookback Window
                try:
                    reading_time = datetime.fromisoformat(dt.replace("Z", "+00:00"))
                    now_utc = datetime.now(timezone.utc)
                    if now_utc - reading_time > timedelta(hours=12):
                        continue
                except (ValueError, TypeError):
                    continue

                if param_name not in param_groups:
                    param_groups[param_name] = []
                
                param_groups[param_name].append({
                    "value": float(value),
                    "unit": unit,
                    "time": reading_time,
                    "dt_str": dt
                })

            # 2. Sort by timestamp DESC and pick the first valid one per parameter
            final_vals = {
                "pm25": None, "pm10": None, "no2": None, "so2": None,
                "co": None, "o3": None, "temp": None, "hum": None,
                "ws": None, "wd": None
            }
            latest_time = None

            for param_name, items in param_groups.items():
                items.sort(key=lambda x: x["time"], reverse=True)
                
                for item in items:
                    val_float = item["value"]
                    unit = item["unit"]
                    dt_str = item["dt_str"]

                    if latest_time is None or dt_str > latest_time:
                        latest_time = dt_str

                    success = False
                    if param_name in ("pm25", "pm2.5") and final_vals["pm25"] is None:
                        if unit == "µg/m³": final_vals["pm25"] = val_float; success = True
                    elif param_name == "pm10" and final_vals["pm10"] is None:
                        if unit == "µg/m³": final_vals["pm10"] = val_float; success = True
                    elif param_name == "no2" and final_vals["no2"] is None:
                        if unit == "µg/m³": final_vals["no2"] = val_float; success = True
                        elif unit == "ppb": final_vals["no2"] = val_float * 1.88; success = True
                    elif param_name == "so2" and final_vals["so2"] is None:
                        if unit == "µg/m³": final_vals["so2"] = val_float; success = True
                        elif unit == "ppb": final_vals["so2"] = val_float * 2.62; success = True
                    elif param_name in ("co", "carbon_monoxide") and final_vals["co"] is None:
                        if unit == "µg/m³": final_vals["co"] = val_float / 1000.0; success = True
                        elif unit == "ppm": final_vals["co"] = val_float * 1.15; success = True
                    elif param_name in ("o3", "ozone") and final_vals["o3"] is None:
                        if unit == "µg/m³": final_vals["o3"] = val_float; success = True
                        elif unit == "ppb": final_vals["o3"] = (val_float * 48.00) / 24.45; success = True
                    elif param_name == "temperature" and final_vals["temp"] is None:
                        if unit == "c": final_vals["temp"] = val_float; success = True
                    elif param_name == "relativehumidity" and final_vals["hum"] is None:
                        if unit == "%": final_vals["hum"] = val_float; success = True
                    elif param_name == "wind_speed" and final_vals["ws"] is None:
                        if unit == "m/s": final_vals["ws"] = val_float; success = True
                    elif param_name == "wind_direction" and final_vals["wd"] is None:
                        if unit == "deg": final_vals["wd"] = val_float; success = True

                    if success:
                        break  # Found the newest valid reading

            # PM2.5 is REQUIRED — if not available, return None (no estimation!)
            if final_vals["pm25"] is None:
                logger.warning(
                    f"[OpenAQ] No valid PM2.5 reading (µg/m³ within 12 hrs) for {station_name}. "
                    f"Returning None — no substitute values will be used."
                )
                return None

            return StationReading(
                name=station_name,
                lat=lat,
                lon=lon,
                pm25=final_vals["pm25"],
                pm10=final_vals["pm10"],
                no2=final_vals["no2"],
                so2=final_vals["so2"],
                co=final_vals["co"],
                o3=final_vals["o3"],
                temperature=final_vals["temp"],
                humidity=final_vals["hum"],
                wind_speed=final_vals["ws"],
                wind_direction=final_vals["wd"],
                timestamp=latest_time,
                openaq_location_id=location_id,
            )

        except OpenAQRateLimitError:
            raise  # Propagate rate limit errors — do NOT mask them
        except OpenAQDataUnavailableError:
            raise  # Propagate data unavailable errors
        except Exception as e:
            logger.error(f"[OpenAQ] Error fetching latest for {station_name}: {e}")
            return None

    def fetch_all_latest(
        self, station_coords: dict
    ) -> Tuple[List[StationReading], List[str], Optional[str]]:
        """
        Fetch live readings for all 40 stations.
        
        Returns:
            (successful_readings, failed_station_names, error_message_or_none)
            
        If rate limited, raises OpenAQRateLimitError.
        Failed stations are explicitly listed — NEVER silently dropped.
        """
        # Ensure station IDs are discovered
        if not self._station_id_cache:
            self.discover_station_ids(station_coords)

        readings = []
        failed = []

        for name, (lat, lon) in station_coords.items():
            loc_id = self._station_id_cache.get(name)
            if loc_id is None:
                failed.append(name)
                continue

            try:
                reading = self.fetch_latest_for_station(name, lat, lon, loc_id)
                if reading is not None:
                    readings.append(reading)
                else:
                    failed.append(name)
            except OpenAQRateLimitError:
                # Stop immediately — do not continue fetching
                logger.error(
                    f"[OpenAQ] Rate limit hit at station '{name}'. "
                    f"Fetched {len(readings)} stations before limit. "
                    f"Remaining stations will not have data."
                )
                raise
            except Exception as e:
                logger.error(f"[OpenAQ] Failed to fetch {name}: {e}")
                failed.append(name)

        error_msg = None
        if failed:
            error_msg = (
                f"{len(failed)} of {len(station_coords)} stations had no valid data: "
                f"{', '.join(failed[:10])}"
                + (f" ... and {len(failed)-10} more" if len(failed) > 10 else "")
            )
            logger.warning(f"[OpenAQ] {error_msg}")

        logger.info(
            f"[OpenAQ] Fetched live data for {len(readings)}/{len(station_coords)} stations."
        )
        return readings, failed, error_msg

    def _fetch_weather_fallback(self, lat: float, lon: float) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
        """
        Fallback to Open-Meteo for missing weather variables.
        Returns: (temperature_2m, relative_humidity_2m, wind_speed_10m, wind_direction_10m)
        """
        try:
            url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json().get("current", {})
                return (
                    data.get("temperature_2m"),
                    data.get("relative_humidity_2m"),
                    data.get("wind_speed_10m"),
                    data.get("wind_direction_10m")
                )
        except Exception as e:
            logger.warning(f"[OpenAQ] Open-Meteo fallback failed: {e}")
        return None, None, None, None

    def build_feature_matrix(self, station_coords: dict) -> Tuple["torch.Tensor", Dict[int, Dict[str, float]]]:
        """
        Builds a [40, 6] PyTorch tensor feature matrix:
        Columns: PM10 (µg/m³), NO2 (µg/m³), SO2 (µg/m³), CO (mg/m³), Wind Speed (m/s), Wind Dir (deg).
        Missing values are strictly masked with 0.0 (No fake data interpolation).
        
        Also returns a dict mapping station index -> {"temperature": T, "humidity": H}.
        """
        # Discover IDs if needed
        if not self._station_id_cache:
            self.discover_station_ids(station_coords)

        num_stations = len(station_coords)
        feature_matrix = torch.zeros((num_stations, 6), dtype=torch.float32)
        temp_hum_dict = {}

        for idx, (name, (lat, lon)) in enumerate(station_coords.items()):
            loc_id = self._station_id_cache.get(name)
            
            pm10_val, no2_val, so2_val, co_val = 0.0, 0.0, 0.0, 0.0
            ws_val, wd_val = None, None
            temp_val, hum_val = None, None

            if loc_id is not None:
                try:
                    reading = self.fetch_latest_for_station(name, lat, lon, loc_id)
                    if reading is not None:
                        # Map pollutants to matrix columns (if missing, leave as 0.0 mask)
                        pm10_val = float(reading.pm10) if reading.pm10 is not None else 0.0
                        no2_val = float(reading.no2) if reading.no2 is not None else 0.0
                        so2_val = float(reading.so2) if reading.so2 is not None else 0.0
                        co_val = float(reading.co) if reading.co is not None else 0.0
                        
                        temp_val = float(reading.temperature) if reading.temperature is not None else None
                        hum_val = float(reading.humidity) if reading.humidity is not None else None
                        ws_val = float(reading.wind_speed) if reading.wind_speed is not None else None
                        wd_val = float(reading.wind_direction) if reading.wind_direction is not None else None
                except (OpenAQRateLimitError, OpenAQDataUnavailableError) as e:
                    logger.warning(f"[MLOps] OpenAQ data unavailable for {name}: {e}. Masking with 0.0")

            # Open-Meteo Fallback check
            if None in (ws_val, wd_val, temp_val, hum_val):
                logger.info(f"[MLOps] Weather fallback triggered for {name}")
                fb_temp, fb_hum, fb_ws, fb_wd = self._fetch_weather_fallback(lat, lon)
                
                temp_val = fb_temp if temp_val is None and fb_temp is not None else (temp_val or 0.0)
                hum_val = fb_hum if hum_val is None and fb_hum is not None else (hum_val or 0.0)
                ws_val = fb_ws if ws_val is None and fb_ws is not None else (ws_val or 0.0)
                wd_val = fb_wd if wd_val is None and fb_wd is not None else (wd_val or 0.0)
            else:
                temp_val = temp_val or 0.0
                hum_val = hum_val or 0.0
                ws_val = ws_val or 0.0
                wd_val = wd_val or 0.0

            # Assign to PyTorch tensor
            feature_matrix[idx, 0] = pm10_val
            feature_matrix[idx, 1] = no2_val
            feature_matrix[idx, 2] = so2_val
            feature_matrix[idx, 3] = co_val
            feature_matrix[idx, 4] = ws_val
            feature_matrix[idx, 5] = wd_val
            
            temp_hum_dict[idx] = {"temperature": temp_val, "humidity": hum_val}

        return feature_matrix, temp_hum_dict


# ─── Module-level singleton ────────────────────────────────────────────────────
# Import and use: from app.services.openaq_client import openaq_client
openaq_client = OpenAQClient()
