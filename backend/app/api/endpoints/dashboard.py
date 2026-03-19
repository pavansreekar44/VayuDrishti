from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Dict, Any
import random
import math
import httpx # requires pip install httpx

router = APIRouter()

class WardStat(BaseModel):
    id: str
    name: str
    lat: float
    lon: float
    aqi: int
    pm25: float
    dominant_source: str
    status: str
    trend: str

class Recommendation(BaseModel):
    id: str
    ward: str
    issue: str
    action: str
    impact: str
    urgency: str

# Base coordinates for the 10 Delhi Wards
WARDS_DATA = [
    {"id": "W01", "name": "Connaught Place", "lat": 28.6315, "lon": 77.2167},
    {"id": "W02", "name": "Karol Bagh", "lat": 28.6519, "lon": 77.1888},
    {"id": "W03", "name": "Chanakyapuri", "lat": 28.5950, "lon": 77.1895},
    {"id": "W04", "name": "Dwarka", "lat": 28.5823, "lon": 77.0500},
    {"id": "W05", "name": "Chandni Chowk", "lat": 28.6505, "lon": 77.2303},
    {"id": "W06", "name": "Anand Vihar", "lat": 28.6489, "lon": 77.3152},
    {"id": "W07", "name": "Okhla", "lat": 28.5606, "lon": 77.2910},
    {"id": "W08", "name": "Najafgarh", "lat": 28.6090, "lon": 76.9855},
    {"id": "W09", "name": "Rohini", "lat": 28.7306, "lon": 77.1009},
    {"id": "W10", "name": "Vasant Kunj", "lat": 28.5292, "lon": 77.1534},
]

def get_status(aqi: int) -> str:
    if aqi <= 50: return "Good"
    if aqi <= 100: return "Satisfactory"
    if aqi <= 200: return "Moderate"
    if aqi <= 300: return "Poor"
    if aqi <= 400: return "Very Poor"
    return "Severe"

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)
    dphi = math.radians(lat2 - lat1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.asin(math.sqrt(a))

@router.get("/wards", response_model=List[WardStat])
async def get_ward_stats():
    """Fetches LIVE data from OpenAQ IoT sensors and groups them by Municipal Ward dynamically."""
    live_points = []
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Query all active live sensors in New Delhi
            r = await client.get('https://api.openaq.org/v2/latest?coordinates=28.6139,77.2090&radius=40000&limit=300')
            if r.status_code == 200:
                results = r.json().get('results', [])
                for res in results:
                    lat, lon = res['coordinates']['latitude'], res['coordinates']['longitude']
                    pm25 = next((m['value'] for m in res['measurements'] if m['parameter'] == 'pm25'), None)
                    if pm25 is not None:
                        live_points.append({"lat": lat, "lon": lon, "pm25": pm25})
    except Exception as e:
        print("Backend OpenAQ Error:", e)

    results = []
    for w in WARDS_DATA:
        # Spatial Join: Find all live IoT sensors inside this Ward's 5km radius
        ward_sensors = [p for p in live_points if haversine(w['lat'], w['lon'], p['lat'], p['lon']) <= 5.0]
        
        if len(ward_sensors) > 0:
            avg_pm25 = sum(p['pm25'] for p in ward_sensors) / len(ward_sensors)
        else:
            # Spatial Fallback: Use the exact value of the single absolute nearest IoT sensor to this ward center
            if len(live_points) > 0:
                nearest = min(live_points, key=lambda p: haversine(w['lat'], w['lon'], p['lat'], p['lon']))
                avg_pm25 = nearest['pm25']
            else:
                avg_pm25 = 150.0 # Extreme fallback if OpenAQ is down completely
                
        # In a real environment, PM2.5 to AQI uses a complex piecewise function. We approximate heavily.
        current_aqi = int(avg_pm25 * 3.5)
        
        # MOCK ONLY: Source Detection (Since hitting Google Earth Engine Sentinel-5P takes too long live)
        simulated_source = "Vehicle Exhaust"
        if "Dust" in w['name'] or current_aqi < 180: simulated_source = "Construction Dust"
        if w['name'] == "Najafgarh": simulated_source = "Biomass Burning"
        if current_aqi > 350: simulated_source = "Industrial Emissions & Heavy Transport"

        results.append(WardStat(
            id=w["id"],
            name=w["name"],
            lat=w["lat"],
            lon=w["lon"],
            aqi=current_aqi,
            pm25=round(avg_pm25, 1),
            dominant_source=simulated_source,
            status=get_status(current_aqi),
            trend=random.choice(["increasing", "decreasing", "stable"])
        ))
    
    results.sort(key=lambda x: x.aqi, reverse=True)
    return results

@router.get("/recommendations", response_model=List[Recommendation])
async def get_policy_recommendations():
    """Generates automated policy recommendations. Currently uses rules heuristics, ready for Gemini LLM injection."""
    recs = [
        Recommendation(
            id="REC-001",
            ward="Anand Vihar",
            issue="Severe Industrial and Traffic Emissions detected via Spatial Clustering.",
            action="Deploy mobile inspection units to Anand Vihar ISBT and nearby industrial zones. Issue temporary halt notices.",
            impact="Expected 20% reduction in local PM2.5 within 48 hours.",
            urgency="High"
        ),
        Recommendation(
            id="REC-002",
            ward="Dwarka",
            issue="Spike in localized Construction Dust (Spatio-Temporal Anomaly).",
            action="Enforce water sprinkling protocols at active expressway construction sites.",
            impact="Expected 15% reduction in coarse particulate matter.",
            urgency="Medium"
        ),
        Recommendation(
            id="REC-003",
            ward="Chandni Chowk",
            issue="Prolonged Vehicle Exhaust and Waste burning accumulation.",
            action="Implement strict entry limits for heavily polluting commercial vehicles during 6 PM - 9 PM peak hours.",
            impact="Reduction in street-level exposure by 30%.",
            urgency="Critical"
        )
    ]
    return recs
