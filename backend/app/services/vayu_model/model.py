import torch
import torch.nn as nn
from torch_geometric.nn import GATConv

# In model.py, update the initialization:
class VayuDrishtiModel(nn.Module):
    def __init__(self, in_features=7, hidden_dim=64, out_features=5, heads=4): # Updated here!
        super(VayuDrishtiModel, self).__init__()
       
        
        self.in_features = in_features
        self.hidden_dim = hidden_dim
        self.out_features = out_features
        self.num_nodes = 250
        
        # ==========================================
        # 1. SPATIAL MECHANISM (GAT)
        # ==========================================
        # We use multiple attention heads to let the model look for different 
        # physical relationships (e.g., Head 1 tracks wind, Head 2 tracks PM mass).
        # We divide hidden_dim by heads so the final concatenated output remains hidden_dim.
        self.gat = GATConv(
            in_channels=in_features, 
            out_channels=hidden_dim // heads, 
            heads=heads, 
            concat=True
        )
        self.relu = nn.ReLU()
        
        # ==========================================
        # 2. TEMPORAL MECHANISM (LSTM)
        # ==========================================
        # batch_first=True means it expects [Batch, Sequence, Features]
        self.lstm = nn.LSTM(
            input_size=hidden_dim, 
            hidden_size=hidden_dim, 
            num_layers=1, 
            batch_first=True
        )
        
        # ==========================================
        # 3. PHYSICAL PROJECTION (No MLP)
        # ==========================================
        # A single linear layer to step down directly from the hidden space 
        # to our 5 target chemicals, forcing the LSTM to learn pure physics.
        self.predictor = nn.Linear(hidden_dim, out_features)

    def forward(self, x, edge_index):
        """
        x shape: [Batch, Seq_Len, 250, 7]
        edge_index shape: [2, num_edges]
        """
        B, Seq, N, F = x.shape
        
        # ---------------------------------------------------------
        # PHASE 1: SPATIAL PROPAGATION
        # We fold the Sequence into the Batch dimension. 
        # 32 batches of 24 hours become 768 independent graphs.
        # ---------------------------------------------------------
        x_flat = x.view(B * Seq * N, F)
        
        # To run 768 graphs through the GAT simultaneously, we must replicate 
        # the edge_index 768 times, shifting the node IDs for each graph 
        # so they don't accidentally connect across time or batches.
        num_graphs = B * Seq
        E = edge_index.size(1)
        
        # Repeat the base connections
        edge_index_batched = edge_index.repeat(1, num_graphs)
        
        # Create an offset (Graph 0 adds 0, Graph 1 adds 250, Graph 2 adds 500...)
        offset = (torch.arange(num_graphs, device=x.device) * N).repeat_interleave(E)
        edge_index_batched = edge_index_batched + offset
        
        # Pass the massive batched graph through the GAT
        gat_out = self.gat(x_flat, edge_index_batched)
        gat_out = self.relu(gat_out)
        
        # ---------------------------------------------------------
        # PHASE 2: TEMPORAL PROPAGATION
        # Unfold the massive graph back to [Batch, Seq, Nodes, Hidden]
        # ---------------------------------------------------------
        gat_out = gat_out.view(B, Seq, N, self.hidden_dim)
        
        # Now, we swap the dimensions. We fold the Nodes into the Batch dimension.
        # This isolates the timeline for every single node so the LSTM can analyze it.
        # Shape becomes: [Batch * Nodes, Seq_Len, Hidden]
        lstm_in = gat_out.transpose(1, 2).reshape(B * N, Seq, self.hidden_dim)
        
        lstm_out, (h_n, c_n) = self.lstm(lstm_in)
        
        # We only care about the final prediction at the end of the sequence window
        # Shape: [Batch * Nodes, Hidden]
        last_timestep = lstm_out[:, -1, :]
        
        # ---------------------------------------------------------
        # PHASE 3: THE DETERMINISTIC FINISH
        # ---------------------------------------------------------
        # Project from Hidden to the 4 target gases
        predictions = self.predictor(last_timestep)
        
        # Unfold back to the final output shape: [Batch, Nodes, 4]
        predictions = predictions.view(B, N, self.out_features)
        
        return predictions

# ==========================================
# QUICK TEST BLOCK
# ==========================================
if __name__ == "__main__":
    print("[*] Instantiating VayuDrishti GAT+LSTM Engine...")
    
    # Simulate data coming from your DataLoader
    batch_size = 32
    seq_len = 24
    num_nodes = 250
    features = 6
    
    dummy_x = torch.randn(batch_size, seq_len, num_nodes, features)
    
    # Load the actual edge index we built in Phase 4
    try:
        real_edge_index = torch.load("delhi_250_8km_edge_index.pt")
        print(f"[*] Loaded true topology with {real_edge_index.size(1)} edges.")
    except FileNotFoundError:
        print("[!] 'delhi_250_8km_edge_index.pt' not found. Using dummy edges for test.")
        # Dummy edge index (Node 0 to Node 1)
        real_edge_index = torch.tensor([[0, 1], [1, 0]], dtype=torch.long)
    
    model = VayuDrishtiModel()
    
    print("[*] Running Forward Pass...")
    output = model(dummy_x, real_edge_index)
    
    print("\n[+] Network Architecture Verification Successful!")
    print(f"    Input Shape : {dummy_x.shape} -> [Batch, Seq, Nodes, Features]")
    print(f"    Output Shape: {output.shape} -> [Batch, Nodes, Targets (PM2.5, PM10, NO2, SO2)]")
