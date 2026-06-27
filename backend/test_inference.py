import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.services.ml_engine import ML_ENGINE

def test():
    # Force run one loop
    ML_ENGINE.run_inference_cycle()
    preds, ts = ML_ENGINE.get_cached_predictions()
    
    if preds:
        wards = list(preds.values())
        print(f"Total wards predicted: {len(wards)}")
        for i in range(5):
            print(f"Ward {wards[i]['name']}: AQI={wards[i]['aqi']} PM2.5={wards[i]['pm25']:.1f}")
            
        print("Max AQI:", max(w['aqi'] for w in wards))
        print("Min AQI:", min(w['aqi'] for w in wards))
        print("Avg AQI:", sum(w['aqi'] for w in wards) / len(wards))
    else:
        print("No predictions returned!")

test()
