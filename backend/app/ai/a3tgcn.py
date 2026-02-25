import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import GCNConv

class AttentionLayer(nn.Module):
    """
    Temporal Attention Mechanism to weigh the importance of different past time steps.
    """
    def __init__(self, hidden_dim):
        super(AttentionLayer, self).__init__()
        self.w_omega = nn.Parameter(torch.Tensor(hidden_dim, hidden_dim))
        self.u_omega = nn.Parameter(torch.Tensor(hidden_dim, 1))

        nn.init.uniform_(self.w_omega, -0.1, 0.1)
        nn.init.uniform_(self.u_omega, -0.1, 0.1)

    def forward(self, inputs):
        # inputs: (batch_size, num_nodes, seq_len, hidden_dim)
        v = torch.tanh(torch.matmul(inputs, self.w_omega))
        # vu: (batch_size, num_nodes, seq_len, 1)
        vu = torch.matmul(v, self.u_omega)
        alphas = F.softmax(vu, dim=2)
        # return weighted average over the time sequence length
        out = torch.sum(inputs * alphas, dim=2)
        return out

class A3TGCN(nn.Module):
    """
    Attention Temporal Graph Convolutional Network (A3T-GCN)
    Combines GCN (Spatial) and GRU (Temporal) with Global Attention.
    """
    def __init__(self, node_features, hidden_dim, seq_len=24):
        """
        node_features: Number of features per node (e.g., historical pollution, SVF, Aspect Ratio)
        hidden_dim: Hidden dimension size for GCN and GRU layers
        seq_len: How many past time steps (hours) we feed into the model
        """
        super(A3TGCN, self).__init__()
        
        # Spatial Graph Convolution
        self.gcn = GCNConv(node_features, hidden_dim)
        
        # Temporal Gated Recurrent Unit
        self.gru = nn.GRU(hidden_dim, hidden_dim, batch_first=True)
        
        # Temporal Attention Mechanism
        self.attention = AttentionLayer(hidden_dim)
        
        # Final Output Layer (Predicting a single pollution value per node)
        self.linear = nn.Linear(hidden_dim, 1)

    def forward(self, x, edge_index):
        # PyTorch Geometric flattens batch and nodes into a single dimension
        # x shape: (num_nodes, seq_len, node_features)
        num_nodes, seq_len, features = x.shape
        
        hidden_states = []
        
        # 1. Process Spatial Data for each time step
        for t in range(seq_len):
            x_t = x[:, t, :] # (num_nodes, node_features)
            
            gcn_out = self.gcn(x_t, edge_index) # (num_nodes, hidden_dim)
            hidden_states.append(gcn_out.unsqueeze(1)) # (num_nodes, 1, hidden_dim)
            
        # 2. Process Temporal sequence
        # hidden_states: (num_nodes, seq_len, hidden_dim)
        hidden_states = torch.cat(hidden_states, dim=1)
        
        # GRU expects (batch, seq, feature) -> (num_nodes, seq_len, hidden_dim)
        gru_out, _ = self.gru(hidden_states)
        
        # 3. Apply Temporal Attention
        # We want to re-insert the batch_size dimension conceptually if needed
        gru_out = gru_out.unsqueeze(0) # (1, num_nodes, seq_len, hidden_dim)
        attention_out = self.attention(gru_out) # (1, num_nodes, hidden_dim)
        
        # 4. Final Prediction across all nodes
        predictions = self.linear(attention_out.squeeze(0)) # (num_nodes, 1)
        return torch.relu(predictions) # Assuming pollution metrics >= 0
