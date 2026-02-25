import torch
import os
from .a3tgcn import A3TGCN
import logging

logger = logging.getLogger(__name__)

class AIPollutionPredictor:
    """
    Singleton wrapper to load the trained A3T-GCN PyTorch weights into memory
    and provide millisecond-latency pollution predictions for the A* Routing Engine.
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(AIPollutionPredictor, cls).__new__(cls)
            cls._instance._initialize(*args, **kwargs)
        return cls._instance

    def _initialize(self, weights_path: str = None):
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.model = A3TGCN(node_features=5, hidden_dim=64, seq_len=24).to(self.device)
        self.is_loaded = False
        
        if not weights_path:
            weights_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "a3tgcn_weights.pt")

        if os.path.exists(weights_path):
            try:
                self.model.load_state_dict(torch.load(weights_path, map_location=self.device, weights_only=True))
                self.model.eval()
                self.is_loaded = True
                self.cached_predictions = self._run_full_inference_pass()
                logger.info(f"✅ Loaded PyTorch AI Brain from {weights_path} and cached 60KM map predictions.")
            except Exception as e:
                logger.error(f"Failed to load AI weights: {e}")
        else:
            logger.warning("No pre-trained A3T-GCN weights found. AI Inference will run in fallback simulation mode.")

    def _run_full_inference_pass(self):
        """
        Runs the entire 60km graph through the A3T-GCN model once and caches the predicted PM2.5 target.
        This provides O(1) latency during A* routing.
        """
        try:
            import pickle
            data_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "synthetic_training_tensor.pkl")
            with open(data_path, 'rb') as f:
                dataset = pickle.load(f)
            
            x = torch.tensor(dataset['x'], dtype=torch.float).to(self.device)
            edge_index = dataset['edge_index']
            mapping = dataset['node_mapping']
            reverse_mapping = {v: k for k, v in mapping.items()}
            
            mapped_edges = []
            for u, v in edge_index:
                if u in mapping and v in mapping:
                    mapped_edges.append([mapping[u], mapping[v]])
            edge_tensor = torch.tensor(mapped_edges, dtype=torch.long).t().contiguous().to(self.device)
            
            with torch.no_grad():
                # Extract the last 24-hour window from the dataset to forecast the "current live" hour
                window_x = x[:, -24:, :]
                out = self.model(window_x, edge_tensor)
                
            predictions = {}
            for i in range(out.shape[0]):
                osmid = reverse_mapping[i]
                predictions[osmid] = float(out[i, 0].item())
                
            return predictions
            
        except Exception as e:
            logger.error(f"Failed to run inference pass: {e}. Falling back to simulated proxy.")
            return None

    def predict_edge_pollution(self, u_id, v_id, edge_data, current_time=None) -> float:
        """
        Retrieves the PyTorch A3T-GCN predicted PM2.5 for this specific road segment.
        """
        if self.is_loaded and self.cached_predictions is not None:
            # The pollution on the edge from u to v is approximately the predicted pollution at node u
            # or the average of u and v. We use u for speed.
            if u_id in self.cached_predictions:
                return float(self.cached_predictions[u_id])
        
        highway = edge_data.get('highway', 'residential')
        if isinstance(highway, list):
            highway = highway[0]  # Take first type if merged
            
        base_pm25 = 45.0 # baseline city pollution
        
        # Simulated emissions profile based on infrastructure classification
        hw = str(highway).lower()
        if hw in ['motorway', 'motorway_link', 'trunk', 'trunk_link']:
            base_pm25 += 110.0  # Heavy traffic, high diesel particulate
        elif hw in ['primary', 'primary_link']:
            base_pm25 += 75.0
        elif hw in ['secondary', 'secondary_link']:
            base_pm25 += 40.0
        elif hw in ['tertiary', 'tertiary_link']:
            base_pm25 += 20.0
        elif hw == 'residential':
            base_pm25 += -10.0  # Cleaner air in neighborhoods
        else:
            base_pm25 += -15.0  # Pedestrian/service roads are cleanest
            
        # Add deterministic micro-variance (spatial hashing based on node coordinates)
        try:
            # Deterministic noise between -5.0 and +5.0 PM2.5 based on node IDs
            noise = float((u_id + v_id) % 100) / 10.0 - 5.0
            base_pm25 += noise
        except:
            pass
            
        # Clip to realistic AQI bounds
        return max(5.0, min(base_pm25, 300.0))
