import asyncio
import os
import sys
import math
import numpy as np
from tabulate import tabulate

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.openaq_client import OpenAQClient
from app.services.ml_engine import TemporalNeuralNetworkMock
from app.core.stations import STATION_COORDS

async def run_blind_station_validation():
    print("===============================================================")
    print("   VAYU DRISHTI — LIVE GAT+LSTM-MLP BLIND STATION TEST         ")
    print("===============================================================")
    print("Fetching live OpenAQ data for all 39 stations...")
    
    client = OpenAQClient()
    try:
        readings, failed, error_msg = client.fetch_all_latest(STATION_COORDS)
    except Exception as e:
        print(f"Error fetching OpenAQ data: {e}")
        return

    print(f"Successfully fetched {len(readings)} live stations.")
    if len(readings) < 5:
        print("Not enough live stations to run a meaningful validation test.")
        return

    # Convert readings to dictionaries matching ml_engine expected anchor format
    anchors_data = []
    for r in readings:
        anchors_data.append({
            "id": r.name,
            "lat": r.lat,
            "lon": r.lon,
            "pm25": r.pm25,
            "pm10": r.pm10,
            "no2": r.no2,
            "so2": r.so2,
            "co_ppb": r.co,
            "ws": r.wind_speed,
            "wd": r.wind_direction
        })

    # Prepare wards meta
    all_wards_meta = [{"id": name, "name": name, "lat": lat, "lon": lon} for name, (lat, lon) in STATION_COORDS.items()]

    print("\nInitializing GAT+LSTM Spatial Inference Engine...")
    engine = TemporalNeuralNetworkMock()

    print("\nStarting Leave-One-Out Cross-Validation (Blind Testing)...")
    results = []
    absolute_errors = []
    
    for target in anchors_data:
        target_id = target["id"]
        actual_pm25 = target["pm25"]
        
        # Create anchors EXCLUDING the target
        blind_anchors = [a for a in anchors_data if a["id"] != target_id]
        
        # Predict
        try:
            predictions = engine.predict(blind_anchors, all_wards_meta)
            pred_data = predictions.get(target_id)
            
            if pred_data:
                pred_pm25 = pred_data["pm25"]
                error = abs(pred_pm25 - actual_pm25)
                
                results.append([
                    target_id,
                    f"{actual_pm25:.1f}",
                    f"{pred_pm25:.1f}",
                    f"{error:.1f}",
                    pred_data.get("dominant_source", "Unknown")
                ])
                absolute_errors.append(error)
        except Exception as e:
            print(f"Error predicting for {target_id}: {e}")

    # Output Results
    print("\n--- VALIDATION RESULTS ---")
    headers = ["Station Name", "Actual PM2.5", "Predicted PM2.5", "Abs Error", "Predicted Source"]
    print(tabulate(results, headers=headers, tablefmt="grid"))
    
    if absolute_errors:
        mae = np.mean(absolute_errors)
        rmse = math.sqrt(np.mean(np.array(absolute_errors)**2))
        
        print("\n===============================================================")
        print("   MODEL ACCURACY METRICS")
        print("===============================================================")
        print(f"  Stations Tested: {len(results)}")
        print(f"  Mean Absolute Error (MAE): {mae:.2f} µg/m³")
        print(f"  Root Mean Squared Error (RMSE): {rmse:.2f} µg/m³")
        print("===============================================================")
        
        # Compare against baseline heuristic (48.0)
        baseline_errors = [abs(48.0 - a["pm25"]) for a in anchors_data if a["id"] in [r[0] for r in results]]
        if baseline_errors:
            base_mae = np.mean(baseline_errors)
            print(f"  Baseline (Static 48.0) MAE: {base_mae:.2f} µg/m³")
            improvement = ((base_mae - mae) / base_mae) * 100
            if improvement > 0:
                print(f"  GAT+LSTM Improvement over Baseline: +{improvement:.1f}%")
            else:
                print(f"  GAT+LSTM Degradation vs Baseline: {improvement:.1f}%")

if __name__ == "__main__":
    asyncio.run(run_blind_station_validation())
