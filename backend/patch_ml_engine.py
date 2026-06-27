import sys
with open("app/services/ml_engine.py", "r") as f:
    content = f.read()

# Add _sensor_map_cache to __init__
content = content.replace(
    "self._station_id_cache: Dict[str, int] = {}",
    "self._station_id_cache: Dict[str, int] = {}\n        self._sensor_map_cache: Dict[int, dict] = {}"
)

# Add sensor map logic to discover_station_ids
old_discover_end = """
            self._station_id_cache[name] = best["id"]
            logger.info(f"[OpenAQ] {name} → ID {best['id']}")
"""
new_discover_end = """
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
"""
content = content.replace(old_discover_end, new_discover_end)

# Rewrite fetch_24h_measurements completely
import re
pattern = re.compile(r'    def fetch_24h_measurements\(self, location_id: int, station_name: str\) -> Dict\[int, dict\]:.*?        return hourly\n', re.DOTALL)

new_fetch = """    def fetch_24h_measurements(self, location_id: int, station_name: str) -> Dict[int, dict]:
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
"""
content = re.sub(pattern, new_fetch, content)

with open("app/services/ml_engine.py", "w") as f:
    f.write(content)
print("ml_engine.py patched successfully.")
