import torch
import torch.nn as nn
from torch_geometric.nn import GATConv

class VayuDrishtiSTGNN(nn.Module):
    def __init__(self, num_nodes=39, dyn_features=6, ctx_features=5, gat_hidden=16, lstm_hidden=32, mlp_hidden=64, heads=2):
        super(VayuDrishtiSTGNN, self).__init__()
        
        self.num_nodes = num_nodes
        self.gat_hidden = gat_hidden * heads 
        
        # 1. The Spatial Bridge
        self.gat = GATConv(in_channels=dyn_features, out_channels=gat_hidden, heads=heads, concat=True)
        
        # 2. The Temporal Engine
        self.lstm = nn.LSTM(input_size=self.gat_hidden, hidden_size=lstm_hidden, batch_first=True)
        
        # --- THE PHYSICAL BOTTLENECK ---
        # Forces the LSTM to output exactly 4 interpretable parameters (NO2, SO2, CO, PM10)
        self.chem_bottleneck = nn.Linear(lstm_hidden, 4) 
        
        # 3. The Final Reactor (MLP)
        # Input = 4 Predicted Chemicals + 5 Local Context Features = 9 Vectors
        self.mlp = nn.Sequential(
            nn.Linear(4 + ctx_features, mlp_hidden),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(mlp_hidden, mlp_hidden // 2),
            nn.ReLU(),
            nn.Linear(mlp_hidden // 2, 1) # Predicts Final PM2.5
        )

    def _get_batched_edge_index(self, edge_index, batch_size, seq_len, device):
        """Dynamically duplicates edges for the flattened batch structure to save Colab RAM."""
        num_graphs = batch_size * seq_len
        batched_edges = []
        for i in range(num_graphs):
            offset = i * self.num_nodes
            batched_edges.append(edge_index + offset)
        return torch.cat(batched_edges, dim=1).to(device)

    def forward(self, x_dyn, x_ctx, edge_index):
        B, T, N, F_dyn = x_dyn.shape
        device = x_dyn.device
        
        # --- PHASE 1: SPATIAL GAT ---
        x_dyn_flat = x_dyn.reshape(B * T * N, F_dyn)
        batched_edges = self._get_batched_edge_index(edge_index, B, T, device)
        gat_out = torch.relu(self.gat(x_dyn_flat, batched_edges))
        
        # --- PHASE 2: TEMPORAL LSTM ---
        gat_out = gat_out.reshape(B, T, N, self.gat_hidden)
        lstm_input = gat_out.permute(0, 2, 1, 3).reshape(B * N, T, self.gat_hidden)
        lstm_out, _ = self.lstm(lstm_input)
        lstm_last_state = lstm_out[:, -1, :] 
        
        # Predict the 4 specific chemicals
        chem_pred = self.chem_bottleneck(lstm_last_state) # Shape: [B * N, 4]
        
        # --- PHASE 3: CONTEXTUAL MLP FUSION ---
        x_ctx_flat = x_ctx.reshape(B * N, -1) # Shape: [B * N, 5]
        fusion_input = torch.cat([chem_pred, x_ctx_flat], dim=1) # Shape: [B * N, 9]
        
        pm25_pred = self.mlp(fusion_input) 
        
        out_pm25 = pm25_pred.reshape(B, N, 1)
        out_chem = chem_pred.reshape(B, N, 4)
        
        return out_pm25, out_chem