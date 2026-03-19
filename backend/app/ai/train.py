import torch
import torch.nn as nn
import torch.optim as optim
from torch_geometric.loader import DataLoader
import logging
from app.ai.dataset import CityPollutionGraphDataset
from app.ai.a3tgcn import A3TGCN

logger = logging.getLogger(__name__)

def train_model(data_dir: str, epochs: int = 50, batch_size: int = 2, lr: float = 0.001):
    """
    Executes the training loop for the A3T-GCN model over the constructed spatial-temporal graph.
    """
    logger.info("Initializing PyTorch Dataset...")
    dataset = CityPollutionGraphDataset(root=data_dir)
    
    # Normally, you'd split this into train/val/test
    train_loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)
    
    # 5 features example: [PM2.5_history_t, PM10_history_t, NO2_history_t, SVF, Aspect_Ratio]
    # We will forecast: PM2.5_t+1
    model = A3TGCN(node_features=5, hidden_dim=32, seq_len=24)
    
    optimizer = optim.Adam(model.parameters(), lr=lr)
    criterion = nn.MSELoss() # L2 Loss for continuous regression problems
    
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model = model.to(device)
    logger.info(f"Training on device: {device}")
    
    model.train()
    
    for epoch in range(epochs):
        epoch_loss = 0.0
        
        for batch in train_loader:
            batch = batch.to(device)
            optimizer.zero_grad()
            
            # Forward pass
            # batch.x shape assumed: (batch_size, num_nodes, seq_len, node_features)
            out = model(batch.x, batch.edge_index)
            
            # Loss calculation
            # out shape: (num_nodes, 1)
            # batch.y shape (target): (num_nodes, 1) -- the ground truth pollution value at time t+1
            loss = criterion(out, batch.y)
            
            loss.backward()
            optimizer.step()
            
            epoch_loss += loss.item()
            
        avg_loss = epoch_loss / max(1, len(train_loader))
        if epoch % 10 == 0:
            logger.info(f"Epoch [{epoch}/{epochs}] - Loss: {avg_loss:.4f}")
            
    logger.info("Training complete. Saving weights...")
    torch.save(model.state_dict(), f"{data_dir}/a3tgcn_weights.pt")
    logger.info("Saved weights to a3tgcn_weights.pt")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import os
    data_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    train_model(data_dir=data_path, epochs=1)
