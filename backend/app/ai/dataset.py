import torch
from torch_geometric.data import Data, Dataset
import pickle
import os

class CityPollutionGraphDataset(Dataset):
    def __init__(self, root, transform=None, pre_transform=None):
        super().__init__(root, transform, pre_transform)
        self.data_filepath = os.path.join(root, 'synthetic_training_tensor.pkl')
        self.dataset = None
        self.x = None
        self.y = None
        self.edge_index = None
        self._load_data()

    def _load_data(self):
        """Loads the pre-synthesized 60KM Hyderabad Tensor."""
        print(f"Loading 60km tensor data from {self.data_filepath}...")
        with open(self.data_filepath, 'rb') as f:
            self.dataset = pickle.load(f)
            
        self.x = torch.tensor(self.dataset['x'], dtype=torch.float)
        self.y = torch.tensor(self.dataset['y'], dtype=torch.float)
        
        # Convert edge index format to [2, num_edges] for PyTorch Geometric
        edges = self.dataset['edge_index']
        mapping = self.dataset['node_mapping']
        
        # Edges are currently string IDs from OSMnx. Map them to our 0...N integer indices.
        mapped_edges = []
        for u, v in edges:
            if u in mapping and v in mapping:
                mapped_edges.append([mapping[u], mapping[v]])
                
        self.edge_index = torch.tensor(mapped_edges, dtype=torch.long).t().contiguous()
        
        print(f"Successfully loaded dataset:")
        print(f" - Nodes (Major Intersections): {self.x.size(0)}")
        print(f" - Temporal Sequence (Hours): {self.x.size(1)}")
        print(f" - Features: {self.x.size(2)}")
        print(f" - Edges: {self.edge_index.size(1)}")

    def len(self):
        # The number of temporal overlapping windows we can sample.
        # If we want a 24-hour sequence length, we can sample (Total_Hours - 24) windows
        seq_len = 24
        return self.x.size(1) - seq_len

    def get(self, idx):
        """
        Extracts a 24-hour window slice for all nodes simultaneously (A3T-GCN format).
        Idx is the starting hour.
        """
        seq_len = 24
        window_x = self.x[:, idx : idx + seq_len, :]
        window_y = self.y[:, idx + seq_len - 1, :] # Predict the final hour's PM2.5 in the window
        
        return Data(x=window_x, edge_index=self.edge_index, y=window_y)
