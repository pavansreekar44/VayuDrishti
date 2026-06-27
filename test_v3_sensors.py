import requests
import json
API_KEY = "a48c3556e253887d4098147a13ff033b81ccd7ac36fede20ff5c3b8eb7be4029"
headers = {"X-API-Key": API_KEY}

# 1. Get a location
resp = requests.get("https://api.openaq.org/v3/locations?coordinates=28.65,77.30&radius=3000", headers=headers)
loc = resp.json()["results"][0]
print(f"Location: {loc['name']} (ID: {loc['id']})")

# 2. Get sensors
sensors = loc.get("sensors", [])
sensor_map = {}
for s in sensors:
    p = s["parameter"]["name"].lower()
    sensor_map[p] = s["id"]
print("Sensors:", sensor_map)

# 3. Fetch measurements for pm25 sensor
pm25_id = sensor_map.get("pm25") or sensor_map.get("pm2.5")
if pm25_id:
    resp = requests.get(f"https://api.openaq.org/v3/sensors/{pm25_id}/measurements?limit=24", headers=headers)
    print("PM2.5 Measurements:")
    results = resp.json().get("results", [])
    for r in results[:3]:
        print(r)

