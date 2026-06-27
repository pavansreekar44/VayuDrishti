import sys
import os
import json

# Add backend to path so imports work
sys.path.insert(0, os.path.dirname(__file__))

from app.core.stations import STATION_COORDS
from app.services.ml_engine import OpenAQ24HFetcher

print("=" * 60)
print("  OpenAQ 24H Fetcher Coverage Test")
print("=" * 60)
print(f"Total anchor stations to fetch: {len(STATION_COORDS)}")

fetcher = OpenAQ24HFetcher()
station_ids = fetcher.discover_station_ids(STATION_COORDS)
print(f"[*] Discovered {len(station_ids)} station IDs from OpenAQ.")

valid_count = 0
for stn_name in STATION_COORDS:
    loc_id = station_ids.get(stn_name)
    if not loc_id:
        print(f"[!] NO location ID found for: {stn_name}")
        continue
        
    data = fetcher.fetch_24h_measurements(loc_id, stn_name)
    
    # Check if this station has any PM2.5 data > 0.0 in the last 24h
    has_valid_data = False
    for h in range(24):
        pm25_val = data[h].get('pm25')
        if pm25_val is not None and pm25_val > 0.0:
            has_valid_data = True
            break
            
    if has_valid_data:
        valid_count += 1
    else:
        print(f"[!] NO valid PM2.5 data found for: {stn_name}")

print("-" * 60)
print(f"Coverage Result: {valid_count} out of {len(STATION_COORDS)} stations returned valid data.")
print(f"Coverage Percentage: {(valid_count / len(STATION_COORDS)) * 100:.1f}%")
print("=" * 60)
