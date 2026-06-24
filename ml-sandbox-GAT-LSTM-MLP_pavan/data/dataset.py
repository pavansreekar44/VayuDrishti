
import pandas as pd
import numpy as np
import torch
from torch.utils.data import Dataset, DataLoader
from sklearn.preprocessing import StandardScaler
import joblib
import os

class VayuDrishtiDataset(Dataset):
    def __init__(self, csv_file, seq_len=12, num_nodes=39, split_ratio=0.8, scaler_path='/kaggle/working/scalers'):
        print(f"Loading data from {csv_file}...")
        self.seq_len = seq_len
        self.num_nodes = num_nodes
        
        df = pd.read_csv(csv_file)
        
        self.dyn_cols = ['NO2', 'SO2', 'CO', 'PM10', 'WS', 'WD'] 
        ctx_cols = ['Temp', 'RH', 'Latitude', 'Longitude', 'Dist_Center']
        target_col = ['PM2.5']
        
        raw_dyn = df[self.dyn_cols].values.astype(np.float32)
        raw_ctx = df[ctx_cols].values.astype(np.float32)
        raw_target = df[target_col].values.astype(np.float32)
        
        # --- LOG TRANSFORMATION (REMOVED FOR BASELINE MODEL) ---
        # raw_dyn[:, 0:4] = np.log1p(np.maximum(raw_dyn[:, 0:4], 0)) 
        # raw_target = np.log1p(np.maximum(raw_target, 0))
        
        num_total_rows = raw_dyn.shape[0]
        self.num_timestamps = num_total_rows // num_nodes
        
        train_hours = int(self.num_timestamps * split_ratio)
        train_rows = train_hours * num_nodes
        
        os.makedirs(scaler_path, exist_ok=True)
        self.dyn_scaler = StandardScaler()
        self.ctx_scaler = StandardScaler()
        self.target_scaler = StandardScaler()

        print("Fitting Z-Score Normalizers STRICTLY on Training Split...")
        self.dyn_scaler.fit(raw_dyn[:train_rows])
        self.ctx_scaler.fit(raw_ctx[:train_rows])
        self.target_scaler.fit(raw_target[:train_rows])
        
        joblib.dump(self.dyn_scaler, f'{scaler_path}/dyn_scaler.pkl')
        joblib.dump(self.ctx_scaler, f'{scaler_path}/ctx_scaler.pkl')
        joblib.dump(self.target_scaler, f'{scaler_path}/target_scaler.pkl')
        
        raw_dyn = self.dyn_scaler.transform(raw_dyn)
        raw_ctx = self.ctx_scaler.transform(raw_ctx)
        raw_target = self.target_scaler.transform(raw_target)

        self.dyn_data = raw_dyn.reshape((self.num_timestamps, num_nodes, len(self.dyn_cols)))
        self.ctx_data = raw_ctx.reshape((self.num_timestamps, num_nodes, len(ctx_cols)))
        self.target_data = raw_target.reshape((self.num_timestamps, num_nodes, 1))

        self.dyn_data = torch.tensor(self.dyn_data, dtype=torch.float32)
        self.ctx_data = torch.tensor(self.ctx_data, dtype=torch.float32)
        self.target_data = torch.tensor(self.target_data, dtype=torch.float32)

    def __len__(self):
        return self.num_timestamps - self.seq_len

    def __getitem__(self, idx):
        x_dyn = self.dyn_data[idx : idx + self.seq_len]
        x_ctx = self.ctx_data[idx + self.seq_len]
        y_pm25 = self.target_data[idx + self.seq_len]
        
        y_chem = self.dyn_data[idx + self.seq_len, :, 0:4] 
        
        return x_dyn, x_ctx, y_pm25, y_chem

def get_dataloaders(csv_file, batch_size=32, seq_len=12, split_ratio=0.8, scaler_path='/kaggle/working/scalers'):
    dataset = VayuDrishtiDataset(csv_file, seq_len=seq_len, num_nodes=39, split_ratio=split_ratio, scaler_path=scaler_path)
    train_size = int(len(dataset) * split_ratio)
    
    train_dataset = torch.utils.data.Subset(dataset, range(0, train_size))
    val_dataset = torch.utils.data.Subset(dataset, range(train_size, len(dataset)))
    
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, num_workers=2, pin_memory=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False, num_workers=2, pin_memory=True)
    
    return train_loader, val_loader, dataset