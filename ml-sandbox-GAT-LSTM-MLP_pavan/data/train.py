import argparse
import torch
import torch.nn as nn
import torch.optim as optim
import os
import math
import time
from dataset import get_dataloaders
from model import VayuDrishtiSTGNN

class EarlyStopping:
    def __init__(self, patience=15, path='/kaggle/working/best_st_gnn_model.pth'):
        self.patience = patience
        self.counter = 0
        self.best_score = None
        self.early_stop = False
        self.val_loss_min = float('inf')
        self.path = path
        self.status_message = ""

    def __call__(self, val_loss, model):
        score = -val_loss
        if self.best_score is None:
            self.best_score = score
            self.save_checkpoint(val_loss, model)
            self.status_message = "--> New Best Model Saved!"
        elif score < self.best_score:
            self.counter += 1
            self.status_message = f"--> (Patience: {self.counter}/{self.patience})"
            if self.counter >= self.patience:
                self.early_stop = True
        else:
            self.best_score = score
            self.save_checkpoint(val_loss, model)
            self.counter = 0
            self.status_message = "--> New Best Model Saved!"

    def save_checkpoint(self, val_loss, model):
        torch.save(model.state_dict(), self.path)
        self.val_loss_min = val_loss

def create_deserted_ward_mask(num_nodes=39, mask_ratio=0.20):
    mask = torch.ones((num_nodes), dtype=torch.bool)
    num_masked = math.ceil(num_nodes * mask_ratio)
    masked_indices = torch.randperm(num_nodes)[:num_masked]
    mask[masked_indices] = False
    return mask

def train_pipeline(loss_type='mse', huber_delta=1.0):
    CSV_FILE = '/kaggle/input/datasets/bvspavansreekar/vayudrishti-gat-lstm-mlp-nologhuber/final_graph_delhi_aqi_5yr.csv'
    EDGE_INDEX_FILE = '/kaggle/input/datasets/bvspavansreekar/vayudrishti-gat-lstm-mlp-nologhuber/delhi_8km_edge_index.pt'
    BATCH_SIZE = 32 
    EPOCHS = 150
    SEQ_LEN = 12
    PATIENCE = 15
    
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Executing VayuDrishti Core on: {device}")
    
    train_loader, val_loader, dataset = get_dataloaders(CSV_FILE, batch_size=BATCH_SIZE, seq_len=SEQ_LEN, scaler_path='/kaggle/working/scalers')
    
    try:
        loaded_topology = torch.load(EDGE_INDEX_FILE, map_location=device)
        if isinstance(loaded_topology, dict):
            if 'edge_index' in loaded_topology:
                edge_index = loaded_topology['edge_index'].to(device)
            else:
                raise KeyError("No 'edge_index' in dict.")
        else:
            edge_index = loaded_topology.to(device)
    except FileNotFoundError:
        print(f"WARNING: {EDGE_INDEX_FILE} not found. Creating local test tensor.")
        src = torch.arange(39).repeat_interleave(39)
        dst = torch.arange(39).repeat(39)
        edge_index = torch.stack([src, dst], dim=0).to(device)

    model = VayuDrishtiSTGNN(
        num_nodes=39, dyn_features=6, ctx_features=5, 
        gat_hidden=16, lstm_hidden=32, mlp_hidden=64, heads=2
    ).to(device)
    
    print("\n" + "="*50)
    if loss_type == 'mse':
        print("EXPERIMENT CONFIGURED: Using Pure MSE Loss")
        optimizer_criterion = nn.MSELoss()
    elif loss_type == 'huber':
        print(f"EXPERIMENT CONFIGURED: Using Huber Loss (delta={huber_delta})")
        optimizer_criterion = nn.HuberLoss(delta=huber_delta)
    print("="*50 + "\n")
        
    mse_logging_criterion = nn.MSELoss() 
    
    optimizer = optim.Adam(model.parameters(), lr=0.001, weight_decay=1e-4)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode='min', factor=0.5, patience=5)
    early_stopping = EarlyStopping(patience=PATIENCE, path='/kaggle/working/best_st_gnn_model.pth')
    
    os.makedirs('/kaggle/working/weights', exist_ok=True)
    
    print("=== Commencing ST-GNN Training Phase (Tracking RMSE) ===")
    for epoch in range(1, EPOCHS + 1):
        epoch_start_time = time.time()
        model.train()
        train_rmse_total = 0
        
        for batch_idx, (x_dyn, x_ctx, y_pm25, y_chem) in enumerate(train_loader):
            x_dyn, x_ctx, y_pm25, y_chem = x_dyn.to(device), x_ctx.to(device), y_pm25.to(device), y_chem.to(device)
            
            mask = create_deserted_ward_mask(num_nodes=39).to(device)
            x_dyn_masked = x_dyn.clone()
            x_dyn_masked[:, :, ~mask, 0:4] = 0.0 
            
            optimizer.zero_grad()
            out_pm25, out_chem = model(x_dyn_masked, x_ctx, edge_index)
            
            # FIX 1: Pure backward gradient calculation (No Square Root)
            loss_pm25 = optimizer_criterion(out_pm25[:, ~mask, :], y_pm25[:, ~mask, :])
            loss_chem = optimizer_criterion(out_chem[:, ~mask, :], y_chem[:, ~mask, :])
            loss = loss_pm25 + loss_chem
            
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            
            # FIX 2: RMSE strictly for console logs (Detached from backward pass)
            with torch.no_grad():
                mse_pm25 = mse_logging_criterion(out_pm25[:, ~mask, :], y_pm25[:, ~mask, :])
                mse_chem = mse_logging_criterion(out_chem[:, ~mask, :], y_chem[:, ~mask, :])
                batch_rmse = torch.sqrt(mse_pm25 + 1e-8) + torch.sqrt(mse_chem + 1e-8)
                train_rmse_total += batch_rmse.item()
            
        train_rmse_total /= len(train_loader)
        
        # --- VALIDATION LOOP ---
        model.eval()
        val_rmse_total = 0
        with torch.no_grad():
            for x_dyn, x_ctx, y_pm25, y_chem in val_loader:
                x_dyn, x_ctx, y_pm25, y_chem = x_dyn.to(device), x_ctx.to(device), y_pm25.to(device), y_chem.to(device)
                
                mask = create_deserted_ward_mask(num_nodes=39).to(device)
                x_dyn_masked = x_dyn.clone()
                x_dyn_masked[:, :, ~mask, 0:4] = 0.0 
                
                out_pm25, out_chem = model(x_dyn_masked, x_ctx, edge_index)
                
                mse_pm25 = mse_logging_criterion(out_pm25[:, ~mask, :], y_pm25[:, ~mask, :])
                mse_chem = mse_logging_criterion(out_chem[:, ~mask, :], y_chem[:, ~mask, :])
                batch_rmse = torch.sqrt(mse_pm25 + 1e-8) + torch.sqrt(mse_chem + 1e-8)
                val_rmse_total += batch_rmse.item()
                
        val_rmse_total /= len(val_loader)
        epoch_duration = time.time() - epoch_start_time
        
        scheduler.step(val_rmse_total)
        early_stopping(val_rmse_total, model)
        
        print(f"Epoch {epoch:03d}/{EPOCHS} [{epoch_duration:.1f}s] | Train RMSE: {train_rmse_total:.4f} | Val RMSE: {val_rmse_total:.4f}  {early_stopping.status_message}")
        
        if early_stopping.early_stop:
            print("-" * 70)
            print(f"Mathematical ceiling reached. Halting early at Epoch {epoch}.")
            break

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VayuDrishti Training Protocol")
    parser.add_argument('--loss', type=str, default='mse', choices=['mse', 'huber'], help="Choose the optimization function")
    parser.add_argument('--delta', type=float, default=1.0, help="Delta threshold if using huber loss")
    args = parser.parse_args()
    
    train_pipeline(loss_type=args.loss, huber_delta=args.delta)