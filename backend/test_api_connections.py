import asyncio
import os
import sys

# Add backend directory to sys.path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.openaq_client import OpenAQClient
from app.services.ml_engine import TemporalNeuralNetworkMock
from app.core.stations import STATION_COORDS

async def test_openaq():
    print("\n--- Testing OpenAQ API (Sensors) ---")
    client = OpenAQClient()
    
    # Just test fetching data for the first 3 stations to avoid rate limits
    stations_to_test = list(STATION_COORDS.keys())[:3]
    
    success_count = 0
    for sid in stations_to_test:
        print(f"Fetching OpenAQ data for {sid}...")
        lat, lon = STATION_COORDS[sid]
        data = await client.fetch_latest_for_station(lat, lon, sid)
        if data:
            print(f"  SUCCESS! Received {len(data)} metrics.")
            print(f"  Sample PM2.5: {data.get('pm25', 'Missing')}")
            print(f"  Sample NO2: {data.get('no2', 'Missing')}")
            success_count += 1
        else:
            print(f"  FAILED or No Data returned.")
            
    return success_count > 0

def test_openweathermap():
    print("\n--- Testing OpenWeatherMap API ---")
    
    # We will instantiate the ml engine just to use its weather function
    # It will automatically pick up the OPENWEATHERMAP_API_KEY from .env
    from dotenv import load_dotenv
    load_dotenv() # Ensure .env is loaded
    
    engine = TemporalNeuralNetworkMock()
    
    if not engine.owm_api_key:
        print("  FAILED: OPENWEATHERMAP_API_KEY is still not loaded or empty in .env!")
        return False
        
    print("  API Key found. Attempting to fetch weather for Connaught Place (Lat: 28.6139, Lon: 77.2090)...")
    
    # Connaught Place coordinates
    temp, rh = engine._fetch_live_weather(28.6139, 77.2090)
    
    # Check if we got the fallback defaults
    if temp == 30.0 and rh == 50.0:
        print("  FAILED: Returned default fallback values (30.0°C, 50.0%). The API call failed. Check your API key or network.")
        return False
    else:
        print(f"  SUCCESS! Live Temp: {temp}°C, Live Humidity: {rh}%")
        return True

async def main():
    print("Starting API Connectivity Tests...\n")
    
    owm_ok = test_openweathermap()
    openaq_ok = await test_openaq()
    
    print("\n--- Summary ---")
    print(f"OpenWeatherMap: {'WORKING' if owm_ok else 'FAILED/FALLBACK'}")
    print(f"OpenAQ Sensors: {'WORKING' if openaq_ok else 'FAILED'}")

if __name__ == "__main__":
    asyncio.run(main())
