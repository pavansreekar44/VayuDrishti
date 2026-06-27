import torch
from torch.utils.data import Dataset
import pandas as pd
import numpy as np
import json
import os

class VayuDrishtiDataset(Dataset):
    def __init__(self, csv_path, seq_len=24):
        print(f"[*] Initializing Dataset and calculating scalars from: {csv_path}")
        df = pd.read_csv(csv_path)
        
        # 1. Define Features (Including CO)
        self.features = ['U', 'V', 'PM2.5 (µg/m³)', 'PM10 (µg/m³)', 'NO2 (µg/m³)', 'SO2 (µg/m³)', 'CO (mg/m³)']
        raw_data = df[self.features].values
        
        # 2. Reshape to 3D [Timesteps, Nodes, Features]
        num_nodes = 250
        num_timesteps = len(raw_data) // num_nodes
        self.data_3d = raw_data.reshape((num_timesteps, num_nodes, len(self.features)))
        
        # 3. Calculate Scalers using Anchor Stations (0-38)
        self.means = np.nanmean(self.data_3d[:, 0:39, :], axis=(0, 1))
        self.stds = np.nanstd(self.data_3d[:, 0:39, :], axis=(0, 1))
        self.stds[self.stds == 0] = 1.0  # Prevent division by zero
        
        # 4. Save Scalers for Production
        # We save this to the output directory so it can be zipped later
        save_dir = "/kaggle/working" if os.path.exists("/kaggle/working") else "."
        scaler_data = {
            "features": self.features,
            "means": self.means.tolist(),
            "stds": self.stds.tolist()
        }
        with open(os.path.join(save_dir, "vayu_scaler.json"), "w") as f:
            json.dump(scaler_data, f)
        print(f"[+] Scalers saved to {os.path.join(save_dir, 'vayu_scaler.json')}")
        
        # 5. Scale Data
        self.data_3d_scaled = (self.data_3d - self.means) / self.stds
        
        # 6. UNIFY MISSING DATA SIGNATURE (The Fix)
        # Force the chemistry features (indices 2 through 6) of the deserted wards (nodes 39-249)
        # to exactly 0.0 in Z-score space. This makes them mathematically identical 
        # to the dynamically masked stations in train.py.
        self.data_3d_scaled[:, 39:, 2:] = 0.0
        
        self.seq_len = seq_len
        
    def __len__(self):
        return len(self.data_3d_scaled) - self.seq_len
        
    def __getitem__(self, idx):
        # Input: 24h window
        X = self.data_3d_scaled[idx : idx + self.seq_len]
        # Target: 5 chemical features only (Indices 2 to 6)
        Y = self.data_3d_scaled[idx + self.seq_len, :, 2:] 
        return torch.FloatTensor(X), torch.FloatTensor(Y)
