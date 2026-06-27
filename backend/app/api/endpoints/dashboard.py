from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import math
import httpx
import json
import os
import asyncio
import time
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# ─── Models ───────────────────────────────────────────────────────────────────

class WardStat(BaseModel):
    name: str
    lat: float
    lon: float
    aqi: int
    pm25: float
    pm10: Optional[float] = 0.0
    no2: Optional[float] = 0.0
    so2: Optional[float] = 0.0
    co: Optional[float] = 0.0
    dominant_source: str
    status: str
    trend: str
    is_station: Optional[bool] = False

class Recommendation(BaseModel):
    id: str
    ward: str
    issue: str
    action: str
    impact: str
    urgency: str

# ─── Config ──────────────────────────────────────────────────────────────────

from app.core.stations import STATION_COORDS, DELHI_CENTER

GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
GCP_LOCATION   = os.environ.get("GCP_LOCATION", "us-central1")

# Auto-detect project ID from the service account credentials file if not set via env var
_CREDS_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'services', 'ee-credentials.json')
if not GCP_PROJECT_ID and os.path.exists(_CREDS_PATH):
    try:
        import json as _json
        _creds = _json.load(open(_CREDS_PATH))
        GCP_PROJECT_ID = _creds.get("project_id")
        if GCP_PROJECT_ID:
            print(f"[GCP] Auto-detected project_id='{GCP_PROJECT_ID}' from ee-credentials.json")
        else:
            print("[GCP] ee-credentials.json has no project_id field")
    except Exception as _e:
        print(f"[GCP] Failed to read credentials for project_id: {_e}")

if not GCP_PROJECT_ID:
    print("[FATAL] GCP_PROJECT_ID not set and could not be read from credentials. Vertex AI will fail.")
else:
    print(f"[GCP] Project: {GCP_PROJECT_ID} | Location: {GCP_LOCATION}")

# ─── Utility Functions ─────────────────────────────────────────────────────────

def pm25_to_aqi_us(pm25: float) -> int:
    """Official US EPA AQI breakpoints for PM2.5 (µg/m³)."""
    bp = [
        (0.0,   12.0,  0,   50),
        (12.1,  35.4,  51,  100),
        (35.5,  55.4,  101, 150),
        (55.5,  150.4, 151, 200),
        (150.5, 250.4, 201, 300),
        (250.5, 350.4, 301, 400),
        (350.5, 500.4, 401, 500),
    ]
    for c_lo, c_hi, i_lo, i_hi in bp:
        if c_lo <= pm25 <= c_hi:
            aqi = i_lo + (pm25 - c_lo) * (i_hi - i_lo) / (c_hi - c_lo)
            return min(int(round(aqi)), 500)
    return 500 if pm25 > 500.4 else 0

def get_status(aqi: int) -> str:
    if aqi <= 50:  return "Good"
    if aqi <= 100: return "Satisfactory"
    if aqi <= 200: return "Moderate"
    if aqi <= 300: return "Poor"
    if aqi <= 400: return "Very Poor"
    return "Severe"

def detect_source(pm25: float, pm10: float, no2: float, co: float, so2: float) -> str:
    """Classify dominant pollution source from atmospheric chemistry."""
    if so2 > 10 and pm25 > 80:
        return "Industrial SO₂ Emissions"
    if no2 > 35 or co > 800:
        return "Vehicle Exhaust & Heavy Traffic"
    if pm10 > 0 and pm25 > 0 and pm10 > (pm25 * 2.2):
        return "Construction & Road Dust"
    if pm25 > 120:
        return "Biomass / Stubble Burning"
    return "Mixed Urban Emissions"

# ─── ML Engine ────────────────────────────────────────────────────────────────

from app.services.ml_engine import ML_ENGINE

# ─── Hourly Background ML Inference Loop ──────────────────────────────────────

BACKGROUND_TASK_STARTED = False

async def _hourly_ml_inference_loop():
    """
    Runs the full ML inference pipeline once per hour.
    The pipeline fetches OpenAQ + OpenMeteo data, runs the model,
    and caches the result. The /wards endpoint serves the cache instantly.
    """
    print("[ML Cron] Hourly ML Inference Loop Started.")

    # Initial run immediately at startup
    await asyncio.get_event_loop().run_in_executor(None, ML_ENGINE.run_inference_cycle)

    while True:
        # Sleep for 1 hour
        await asyncio.sleep(3600)
        try:
            print("[ML Cron] Starting scheduled hourly inference cycle...")
            await asyncio.get_event_loop().run_in_executor(None, ML_ENGINE.run_inference_cycle)
        except Exception as e:
            print(f"[ML Cron] Hourly cycle error (will retry in 1h): {e}")


# ─── API Endpoints ─────────────────────────────────────────────────────────────

@router.get("/wards", response_model=List[WardStat])
async def get_ward_stats(level: str = 'ward'):
    """
    Returns live AQI data from the cached ML inference results.
    - level=ward → full 250-node ML predictions (default)
    - level=district → filtered to CPCB stations only
    """
    global BACKGROUND_TASK_STARTED
    if not BACKGROUND_TASK_STARTED:
        asyncio.create_task(_hourly_ml_inference_loop())
        BACKGROUND_TASK_STARTED = True

    # Wait up to 120s for first ML cycle to complete (24h fetch takes time)
    for _ in range(1200):
        cache, ts, err = ML_ENGINE.get_cached_predictions()
        if cache:
            break
        await asyncio.sleep(0.1)

    cache, ts, err = ML_ENGINE.get_cached_predictions()

    if err and not cache:
        raise HTTPException(status_code=503, detail=err)

    if not cache:
        raise HTTPException(
            status_code=503,
            detail="ML inference has not completed yet. Please retry in a few minutes."
        )

    if level == 'district':
        # Return only CPCB station predictions
        station_results = [
            WardStat(**v) for v in cache.values() if v.get('is_station')
        ]
        station_results.sort(key=lambda x: x.aqi, reverse=True)
        return station_results

    # Ward mode: return all 250 predictions
    all_results = [WardStat(**v) for v in cache.values()]
    all_results.sort(key=lambda x: x.aqi, reverse=True)
    return all_results


@router.get("/recommendations", response_model=List[Recommendation])
async def get_policy_recommendations():
    """
    Generates real-time policy recommendations via Google Gemini.
    AI calls are fully logged and monitored for repetition (reliability guard).
    """
    import re, hashlib

    # Wait for ML cache
    for _ in range(600):
        cache, ts, err = ML_ENGINE.get_cached_predictions()
        if cache:
            break
        await asyncio.sleep(0.1)

    cache, _, _ = ML_ENGINE.get_cached_predictions()
    if not cache:
        raise HTTPException(status_code=503, detail="No inference data available yet")

    # Get top 5 worst zones
    sorted_preds = sorted(cache.values(), key=lambda x: x['aqi'], reverse=True)
    bad_zones = sorted_preds[:5]

    try:
        hotspot_text = "\n".join(
            f"- {z['name']}: AQI {z['aqi']} (PM2.5: {z['pm25']} µg/m³, Source: {z['dominant_source']})"
            for z in bad_zones
        )
        prompt = (
            "You are the Chief Environmental Officer of Delhi Municipal Corporation.\n"
            "The following are the top 5 real-time AQI hotspots right now:\n"
            f"{hotspot_text}\n\n"
            "Generate exactly 3 precise, actionable policy interventions.\n"
            "Output ONLY a raw JSON array (no markdown, no explanation):\n"
            '[{"id":"REC-1","ward":"<zone>","issue":"<1 sentence>","action":"<1 sentence>","impact":"<1 sentence>","urgency":"Critical|High|Medium"}]'
        )

        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:8]
        ai_start = time.time()
        print(f"[AI] Gemini request starting | prompt_hash={prompt_hash} | hotspots={len(bad_zones)}")

        from google import genai
        client = genai.Client(vertexai=True, project=GCP_PROJECT_ID, location='global')

        response = await client.aio.models.generate_content(
            model='gemini-3.1-pro-preview',
            contents=prompt
        )
        text = response.text
        ai_elapsed = int((time.time() - ai_start) * 1000)
        response_hash = hashlib.md5(text.encode()).hexdigest()[:8]
        print(f"[AI] Gemini response | elapsed={ai_elapsed}ms | response_hash={response_hash} | length={len(text)}")

        # ── Repetition Detection Guard ───────────────────────────────────────
        if not hasattr(get_policy_recommendations, "_response_hashes"):
            get_policy_recommendations._response_hashes = []
        recent = get_policy_recommendations._response_hashes
        if recent.count(response_hash) >= 3:
            print(f"[AI] ⚠ REPETITION DETECTED: response_hash={response_hash} appeared {recent.count(response_hash)}x in last {len(recent)} calls. AI may be unreliable.")
        recent.append(response_hash)
        if len(recent) > 10:
            recent.pop(0)

        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            recs_data = json.loads(match.group(0))
            return [Recommendation(**r) for r in recs_data[:3]]

        raise ValueError(f"AI response did not contain valid JSON array (hash={response_hash})")

    except Exception as e:
        print(f"[AI] Gemini FAILURE: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"AI policy engine failed: {str(e)}"
        )

# ─── Feature 4: Wind Grid (MeteoJSON format) ──────────────────────────────────

@router.get("/weather/wind-grid")
async def get_wind_grid():
    """
    Returns a 10x10 wind grid covering Delhi in MeteoJSON format (leaflet-velocity).
    """
    lat_num = 10
    lon_num = 10
    lat_max, lat_min = 28.9, 28.4
    lon_min, lon_max = 76.8, 77.4
    dlat = (lat_max - lat_min) / (lat_num - 1)
    dlon = (lon_max - lon_min) / (lon_num - 1)

    lats, lons = [], []
    for j in range(lat_num):
        lat = lat_max - (j * dlat)
        for i in range(lon_num):
            lon = lon_min + (i * dlon)
            lats.append(round(float(lat), 4))
            lons.append(round(float(lon), 4))

    url = f"https://api.open-meteo.com/v1/forecast?latitude={','.join(map(str, lats))}&longitude={','.join(map(str, lons))}&current=wind_speed_10m,wind_direction_10m"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url)
        if resp.status_code != 200:
            raise HTTPException(status_code=503, detail="Open-Meteo API failed to return wind data.")
        data = resp.json()

    if not isinstance(data, list):
        data = [data]

    import math
    u_vals, v_vals = [], []
    for item in data:
        current = item.get("current", {})
        spd = current.get("wind_speed_10m", 0)
        dir_deg = current.get("wind_direction_10m", 0)

        spd_ms = spd / 3.6
        rad = math.radians(dir_deg)
        u_vals.append(round(-spd_ms * math.sin(rad), 2))
        v_vals.append(round(-spd_ms * math.cos(rad), 2))

    return [
        {
            "header": {
                "parameterCategory": 2, "parameterNumber": 2, "parameterUnit": "m.s-1",
                "dx": dlon, "dy": dlat,
                "la1": lat_max, "la2": lat_min,
                "lo1": lon_min, "lo2": lon_max,
                "nx": lon_num, "ny": lat_num
            },
            "data": u_vals
        },
        {
            "header": {
                "parameterCategory": 2, "parameterNumber": 3, "parameterUnit": "m.s-1",
                "dx": dlon, "dy": dlat,
                "la1": lat_max, "la2": lat_min,
                "lo1": lon_min, "lo2": lon_max,
                "nx": lon_num, "ny": lat_num
            },
            "data": v_vals
        }
    ]
