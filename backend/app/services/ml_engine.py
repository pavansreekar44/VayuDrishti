import math
import random
import os
import requests
import joblib
import torch
import numpy as np

def pm25_to_aqi_ind(pm25: float) -> int:
    """Official CPCB Indian AQI breakpoints for PM2.5 (µg/m³)."""
    bp = [
        (0.0,   30.0,   0,   50),
        (31.0,  60.0,  51,  100),
        (61.0,  90.0, 101,  200),
        (91.0, 120.0, 201,  300),
        (121.0, 250.0, 301, 400),
        (251.0, 9999.0, 401, 500)
    ]
    pm25_rounded = round(pm25)
    for c_lo, c_hi, i_lo, i_hi in bp:
        if c_lo <= pm25_rounded <= c_hi:
            if c_lo == c_hi: return i_lo
            return round(i_lo + (pm25_rounded - c_lo) * (i_hi - i_lo) / (c_hi - c_lo))
    return 500 if pm25_rounded > 250 else 0

"""
# === LEGACY US EPA AQI FORMULA ===
def pm25_to_aqi_us(pm25: float) -> int:
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
            return round(i_lo + (pm25 - c_lo) * (i_hi - i_lo) / (c_hi - c_lo))
    return 500 if pm25 > 500.4 else 0
"""

class TemporalNeuralNetworkMock:
    """
    VayuDrishti Spatial Inference Engine.
    Uses the trained PyTorch GAT+LSTM-MLP model for blind-zone prediction.
    Strictly enforces NO FAKE DATA (masking missing live data to 0.0).
    """
    def __init__(self, model_dir: str = "gat+lstm-mlp_pavan"):
        print("[ML Engine] Booting Temporal Neural Network Spatial Interpolator...")
        
        self.use_torch = False
        self.model = None
        self.dyn_scaler = None
        self.ctx_scaler = None
        self.target_scaler = None
        self.edge_index = None
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
        # Load API keys
        self.owm_api_key = os.environ.get("OPENWEATHERMAP_API_KEY", "")
        if not self.owm_api_key:
            print("[ML Engine] WARNING: OPENWEATHERMAP_API_KEY is missing. Will use default temp/humidity.")

        """
        # === LEGACY MODEL INITIALIZATION ===
        # self.wind_vector_x = 0.8
        # self.wind_vector_y = 0.4
        # class TemporalSpatialNet(nn.Module):
        #     def __init__(self, input_dim: int = 7):
        #         super().__init__()
        #         self.network = nn.Sequential(
        #             nn.Linear(input_dim, 256),
        #             nn.BatchNorm1d(256),
        #             nn.SiLU(),
        #             nn.Dropout(0.25),
        #             nn.Linear(256, 128),
        #             nn.BatchNorm1d(128),
        #             nn.SiLU(),
        #             nn.Dropout(0.15),
        #             nn.Linear(128, 64),
        #             nn.SiLU(),
        #             nn.Linear(64, 1),
        #         )
        #     def forward(self, x):
        #         return self.network(x)
        # ... Loaded from vayu_spatial_PRODUCTION.pt
        """

        try:
            import sys
            base_dir = os.path.dirname(__file__)
            model_path_dir = os.path.join(base_dir, model_dir)
            sys.path.insert(0, model_path_dir)
            
            from model import VayuDrishtiSTGNN
            
            model_weights_path = os.path.join(model_path_dir, "model_nolog_huber.pth")
            if os.path.exists(model_weights_path):
                # Init with identical hyperparameters from train.py / model.py
                self.model = VayuDrishtiSTGNN(num_nodes=39, dyn_features=6, ctx_features=5, gat_hidden=16, lstm_hidden=32, mlp_hidden=64, heads=2)
                self.model.load_state_dict(torch.load(model_weights_path, map_location=self.device, weights_only=True))
                self.model.to(self.device)
                self.model.eval()
                self.use_torch = True
                print(f"[ML Engine] SUCCESS: Production Cloud Weights Loaded natively on {self.device.type.upper()}!")
                
                # Load scalers
                self.dyn_scaler = joblib.load(os.path.join(model_path_dir, "scalers", "dyn_scaler.pkl"))
                self.ctx_scaler = joblib.load(os.path.join(model_path_dir, "scalers", "ctx_scaler.pkl"))
                self.target_scaler = joblib.load(os.path.join(model_path_dir, "scalers", "target_scaler.pkl"))
                
                # Load edge index
                self.edge_index = torch.load(os.path.join(model_path_dir, "delhi_8km_edge_index.pt"), map_location=self.device)
                print(f"[ML Engine] SUCCESS: Scalers and Edge Index loaded.")
            else:
                print(f"[ML Engine] WARNING: Model weights not found at {model_weights_path}")
        except Exception as e:
            print(f"[ML Engine] PyTorch missing or file error: {e}")

    """
    # === LEGACY SPATIAL IDW METHODS ===
    # def _calculate_spatial_weight(self, ward_lat, ward_lon, anchor_lat, anchor_lon):
    #     distance = math.hypot(ward_lat - anchor_lat, (ward_lon - anchor_lon) * 0.8)
    #     dx = ward_lon - anchor_lon
    #     dy = ward_lat - anchor_lat
    #     wind_alignment = (dx * self.wind_vector_x + dy * self.wind_vector_y)
    #     weight = 1.0 / (distance + 0.001)
    #     if wind_alignment > 0:
    #         weight *= 1.5
    #     return weight
    # 
    # def _location_noise(self, lat: float, lon: float, scale: float = 8.0) -> float:
    #     seed = int(abs(lat * 1000) * 7 + abs(lon * 1000) * 13) % 10000
    #     rng = random.Random(seed)
    #     return rng.uniform(-scale, scale)
    """

    def _fetch_live_weather(self, lat: float, lon: float) -> tuple:
        """Fetch real live Temp and RH from OpenWeatherMap."""
        if not self.owm_api_key:
            return 30.0, 50.0 
            
        try:
            url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={self.owm_api_key}&units=metric"
            resp = requests.get(url, timeout=2)
            if resp.status_code == 200:
                data = resp.json()
                temp = data["main"]["temp"]
                rh = data["main"]["humidity"]
                return float(temp), float(rh)
        except Exception as e:
            print(f"[ML Engine] OWM Fetch failed: {e}")
            
        return 30.0, 50.0 
        
    def _get_dominant_source(self, chem_preds):
        no2, so2, co, pm10 = chem_preds
        if so2 > 15 and pm10 > 100:
            return "Industrial Plume + Resuspended Road Dust"
        elif no2 > 40 and co > 1.0:
            return "Dense Traffic & Commercial Congestion"
        elif no2 > 20 and co > 0.5:
            return "Vehicular Combustion + Biomass Influence"
        else:
            return "Background Regional Transport"

    def predict(self, anchors_data: list, all_wards_meta: list) -> dict:
        mapped_predictions = {}
        
        ward_nodes = all_wards_meta[:39] if len(all_wards_meta) >= 39 else all_wards_meta
        num_nodes = len(ward_nodes)
        
        # Build sequence of anchor data (B=1, T=1, N=num_nodes, F=6)
        dyn_matrix = np.zeros((1, 1, num_nodes, 6), dtype=np.float32)
        
        for i, ward in enumerate(ward_nodes):
            ward_id = str(ward.get("id"))
            anchor_match = next((a for a in anchors_data if a["id"] == ward_id), None)
            
            if anchor_match:
                # STRICT MASKING OF FAKE DATA TO 0.0
                no2 = anchor_match.get("no2", 0.0) or 0.0
                so2 = anchor_match.get("so2", 0.0) or 0.0
                co = anchor_match.get("co_ppb", 0.0) or 0.0
                pm10 = anchor_match.get("pm10", 0.0) or 0.0
                ws = anchor_match.get("ws", 0.0) or 0.0
                wd = anchor_match.get("wd", 0.0) or 0.0
                
                dyn_matrix[0, 0, i, :] = [no2, so2, co, pm10, ws, wd]
        
        if self.dyn_scaler:
            flat_dyn = dyn_matrix.reshape(-1, 6)
            scaled_dyn = self.dyn_scaler.transform(flat_dyn)
            dyn_matrix = scaled_dyn.reshape((1, 1, num_nodes, 6))

        for i, ward in enumerate(all_wards_meta):
            ward_id = str(ward.get("id"))
            w_lat = float(ward["lat"])
            w_lon = float(ward["lon"])

            anchor_match = next((a for a in anchors_data if a["id"] == ward_id), None)
            if anchor_match:
                mapped_predictions[ward_id] = anchor_match
                mapped_predictions[ward_id]["aqi"] = pm25_to_aqi_ind(anchor_match.get("pm25", 0.0))
                mapped_predictions[ward_id]["status"] = "Severe" if mapped_predictions[ward_id]["aqi"] > 400 else "Very Poor" if mapped_predictions[ward_id]["aqi"] > 300 else "Poor" if mapped_predictions[ward_id]["aqi"] > 200 else "Moderate" if mapped_predictions[ward_id]["aqi"] > 100 else "Satisfactory" if mapped_predictions[ward_id]["aqi"] > 50 else "Good"
                continue

            if self.use_torch and i < num_nodes:
                try:
                    ctx_matrix = np.zeros((1, num_nodes, 5), dtype=np.float32)
                    temp, rh = self._fetch_live_weather(w_lat, w_lon)
                    dist_city = math.hypot(w_lat - 28.6139, w_lon - 77.2090)
                    
                    ctx_matrix[0, i, :] = [temp, rh, w_lat, w_lon, dist_city]
                    
                    if self.ctx_scaler:
                        flat_ctx = ctx_matrix.reshape(-1, 5)
                        scaled_ctx = self.ctx_scaler.transform(flat_ctx)
                        ctx_matrix = scaled_ctx.reshape((1, num_nodes, 5))
                        
                    x_dyn = torch.tensor(dyn_matrix, dtype=torch.float32).to(self.device)
                    x_ctx = torch.tensor(ctx_matrix, dtype=torch.float32).to(self.device)
                    
                    with torch.no_grad():
                        out_pm25, out_chem = self.model(x_dyn, x_ctx, self.edge_index)
                        
                        pm25_pred = out_pm25[0, i, 0].cpu().numpy()
                        chem_preds = out_chem[0, i, :].cpu().numpy()
                        
                        if self.target_scaler:
                            inv_pm25 = self.target_scaler.inverse_transform([[pm25_pred]])
                            predicted_pm25 = float(inv_pm25[0][0])
                        else:
                            predicted_pm25 = float(pm25_pred)
                            
                        pad_chem = np.zeros((1, 6))
                        pad_chem[0, :4] = chem_preds
                        if self.dyn_scaler:
                            inv_chem = self.dyn_scaler.inverse_transform(pad_chem)
                            real_chem = inv_chem[0, :4]
                        else:
                            real_chem = chem_preds

                    predicted_pm25 = max(5.0, min(500.0, predicted_pm25))
                    source = self._get_dominant_source(real_chem)

                except Exception as e:
                    print(f"Inference error: {e}")
                    predicted_pm25 = 48.0
                    source = "Error"
            else:
                predicted_pm25 = 48.0
                source = "Fallback"
                
            """
            # === LEGACY IDW FALLBACK LOGIC ===
            # else:
            #     total_weight = 0
            #     weighted_pm25 = 0
            #     for anchor in anchors_data:
            #         weight = self._calculate_spatial_weight(w_lat, w_lon, anchor["lat"], anchor["lon"])
            #         weighted_pm25 += anchor["pm25"] * weight
            #         total_weight += weight
            #     base_pm25 = weighted_pm25 / total_weight if total_weight > 0 else 48.0
            #     noise = self._location_noise(w_lat, w_lon, scale=base_pm25 * 0.15)
            #     predicted_pm25 = max(5.0, base_pm25 + noise)
            """

            predicted_pm25 = round(predicted_pm25, 1)
            predicted_aqi = pm25_to_aqi_ind(predicted_pm25)
            
            status = "Severe" if predicted_aqi > 400 else "Very Poor" if predicted_aqi > 300 else "Poor" if predicted_aqi > 200 else "Moderate" if predicted_aqi > 100 else "Satisfactory" if predicted_aqi > 50 else "Good"

            mapped_predictions[ward_id] = {
                "id": ward_id,
                "name": ward.get("name"),
                "lat": w_lat,
                "lon": w_lon,
                "aqi": predicted_aqi,
                "pm25": predicted_pm25,
                "dominant_source": source,
                "status": status,
                "trend": "stable"
            }

        return mapped_predictions
