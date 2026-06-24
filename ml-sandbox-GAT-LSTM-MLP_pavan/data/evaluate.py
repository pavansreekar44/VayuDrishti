
import torch
import numpy as np
import joblib
import math
from sklearn.metrics import mean_squared_error, mean_absolute_error
from dataset import get_dataloaders
from model import VayuDrishtiSTGNN

def create_deserted_ward_mask(num_nodes=39, mask_ratio=0.20):
    mask = torch.ones((num_nodes), dtype=torch.bool)
    num_masked = math.ceil(num_nodes * mask_ratio)
    masked_indices = torch.randperm(num_nodes)[:num_masked]
    mask[masked_indices] = False
    return mask

def evaluate_physical_metrics():
    CSV_FILE = '/kaggle/input/datasets/bvspavansreekar/vayudrishti-gat-lstm-mlp-nologhuber/final_graph_delhi_aqi_5yr.csv'
    EDGE_INDEX_FILE = '/kaggle/input/datasets/bvspavansreekar/vayudrishti-gat-lstm-mlp-nologhuber/delhi_8km_edge_index.pt'
    MODEL_WEIGHTS = '/kaggle/working/best_st_gnn_model.pth'
    SCALER_DIR = '/kaggle/working/scalers'
    
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Loading VayuDrishti Evaluation on: {device}")
    
    _, val_loader, _ = get_dataloaders(CSV_FILE, batch_size=32, seq_len=12)
    
    try:
        loaded_topology = torch.load(EDGE_INDEX_FILE, map_location=device)
        if isinstance(loaded_topology, dict):
            edge_index = loaded_topology['edge_index'].to(device)
        else:
            edge_index = loaded_topology.to(device)
    except FileNotFoundError:
        print(f"WARNING: {EDGE_INDEX_FILE} not found. Creating local test tensor.")
        src = torch.arange(39).repeat_interleave(39)
        dst = torch.arange(39).repeat(39)
        edge_index = torch.stack([src, dst], dim=0).to(device)
        
    dyn_scaler = joblib.load(f'{SCALER_DIR}/dyn_scaler.pkl')
    target_scaler = joblib.load(f'{SCALER_DIR}/target_scaler.pkl')
    
    model = VayuDrishtiSTGNN(num_nodes=39).to(device)
    model.load_state_dict(torch.load(MODEL_WEIGHTS, map_location=device))
    model.eval()
    
    all_pm25_pred, all_pm25_true = [], []
    all_chem_pred, all_chem_true = [], []
    
    print("Running Inference on Validation Set (Deserted Wards Only)...")
    
    with torch.no_grad():
        for x_dyn, x_ctx, y_pm25, y_chem in val_loader:
            x_dyn, x_ctx = x_dyn.to(device), x_ctx.to(device)
            y_pm25, y_chem = y_pm25.cpu().numpy(), y_chem.cpu().numpy()
            
            mask = create_deserted_ward_mask(num_nodes=39)
            x_dyn_masked = x_dyn.clone()
            x_dyn_masked[:, :, ~mask, 0:4] = 0.0 
            
            out_pm25, out_chem = model(x_dyn_masked, x_ctx, edge_index)
            out_pm25, out_chem = out_pm25.cpu().numpy(), out_chem.cpu().numpy()
            
            blind_pm25_pred = out_pm25[:, ~mask, :].reshape(-1, 1)
            blind_pm25_true = y_pm25[:, ~mask, :].reshape(-1, 1)
            
            blind_chem_pred = out_chem[:, ~mask, :].reshape(-1, 4)
            blind_chem_true = y_chem[:, ~mask, :].reshape(-1, 4)
            
            all_pm25_pred.append(blind_pm25_pred)
            all_pm25_true.append(blind_pm25_true)
            all_chem_pred.append(blind_chem_pred)
            all_chem_true.append(blind_chem_true)
            
    final_pm25_pred = np.vstack(all_pm25_pred)
    final_pm25_true = np.vstack(all_pm25_true)
    final_chem_pred = np.vstack(all_chem_pred)
    final_chem_true = np.vstack(all_chem_true)
    
    print("Applying Inverse Transformations (Z-Score Only)...")
    
    # 1. Reverse the Z-Score for PM2.5
    real_pm25_pred = target_scaler.inverse_transform(final_pm25_pred)
    real_pm25_true = target_scaler.inverse_transform(final_pm25_true)
    
    # 2. Reverse the Log Transformation for PM2.5 (REMOVED)
    # real_pm25_pred = np.expm1(real_pm25_pred)
    # real_pm25_true = np.expm1(real_pm25_true)
    
    def inverse_transform_chemistry(chem_array, scaler):
        dummy = np.zeros((chem_array.shape[0], 6))
        dummy[:, 0:4] = chem_array
        inversed_dummy = scaler.inverse_transform(dummy)
        return inversed_dummy[:, 0:4]
        
    # 3. Reverse the Z-Score for Chemistry (NO2, SO2, CO, PM10)
    real_chem_pred = inverse_transform_chemistry(final_chem_pred, dyn_scaler)
    real_chem_true = inverse_transform_chemistry(final_chem_true, dyn_scaler)
    
    # 4. Reverse the Log Transformation for Chemistry (REMOVED)
    # real_chem_pred = np.expm1(real_chem_pred)
    # real_chem_true = np.expm1(real_chem_true)
    
    pm25_rmse = math.sqrt(mean_squared_error(real_pm25_true, real_pm25_pred))
    no2_rmse = math.sqrt(mean_squared_error(real_chem_true[:, 0], real_chem_pred[:, 0]))
    so2_rmse = math.sqrt(mean_squared_error(real_chem_true[:, 1], real_chem_pred[:, 1]))
    co_rmse = math.sqrt(mean_squared_error(real_chem_true[:, 2], real_chem_pred[:, 2]))
    pm10_rmse = math.sqrt(mean_squared_error(real_chem_true[:, 3], real_chem_pred[:, 3]))
    
    pm25_mae = mean_absolute_error(real_pm25_true, real_pm25_pred)
    pm10_mae = mean_absolute_error(real_chem_true[:, 3], real_chem_pred[:, 3])
    
    print("\n" + "="*50)
    print("VAYUDRISHTI FINAL PHYSICAL METRICS (BLIND WARDS)")
    print("="*50)
    print(f"Final PM2.5 RMSE : {pm25_rmse:.2f} µg/m³")
    print(f"Final PM2.5 MAE  : {pm25_mae:.2f} µg/m³ <--- (True baseline error)")
    print("-" * 50)
    print("Source Apportionment Vectors:")
    print(f"NO2 RMSE         : {no2_rmse:.2f} µg/m³")
    print(f"SO2 RMSE         : {so2_rmse:.2f} µg/m³")
    print(f"CO RMSE          : {co_rmse:.2f} mg/m³")
    print(f"PM10 RMSE        : {pm10_rmse:.2f} µg/m³ (Spike Penalty)")
    print(f"PM10 MAE         : {pm10_mae:.2f} µg/m³ <--- (True baseline error)")
    print("="*50)

if __name__ == "__main__":
    evaluate_physical_metrics()