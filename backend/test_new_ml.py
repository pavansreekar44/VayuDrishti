from app.services.ml_engine import TemporalNeuralNetworkMock

def test_ml():
    engine = TemporalNeuralNetworkMock()
    
    # Mock anchors_data
    anchors = [
        {"id": "ward_1", "lat": 28.6139, "lon": 77.2090, "pm25": 100, "no2": 20, "so2": 5, "co_ppb": 0.5, "pm10": 120, "ws": 1.5, "wd": 180}
    ]
    
    # Mock wards metadata (we need 39 wards since the model expects num_nodes=39)
    wards = []
    for i in range(1, 40):
        wards.append({
            "id": f"ward_{i}", 
            "name": f"Ward {i}", 
            "lat": 28.6139 + (i * 0.01), 
            "lon": 77.2090 + (i * 0.01)
        })
    
    preds = engine.predict(anchors, wards)
    print("\n--- Predictions Output ---")
    for k, v in preds.items():
        if k in ["ward_1", "ward_2"]:  # Print just the first two to keep output clean
            print(f"Ward: {v['name']}, AQI: {v['aqi']}, PM2.5: {v['pm25']}, Source: {v['dominant_source']}, Status: {v['status']}")

if __name__ == "__main__":
    test_ml()
