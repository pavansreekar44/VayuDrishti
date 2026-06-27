"""Quick verification that the new VayuDrishti model loads and forward-passes correctly."""
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app', 'services', 'vayu_model'))

import torch
import json

MODEL_DIR = os.path.join(os.path.dirname(__file__), 'app', 'services', 'vayu_model')

print("=" * 60)
print("  VayuDrishti Model Verification Test")
print("=" * 60)

# 1. Load model architecture
from model import VayuDrishtiModel
model = VayuDrishtiModel(in_features=7, hidden_dim=64, out_features=5, heads=4)
print(f"[✓] Model architecture instantiated")

# 2. Load weights
weights_path = os.path.join(MODEL_DIR, "vayu_drishti_final.pth")
model.load_state_dict(torch.load(weights_path, map_location='cpu', weights_only=True))
model.eval()
print(f"[✓] Weights loaded from {os.path.basename(weights_path)}")

# 3. Load edge index
ei_path = os.path.join(MODEL_DIR, "delhi_250_8km_edge_index.pt")
edge_index = torch.load(ei_path, map_location='cpu', weights_only=True)
if isinstance(edge_index, dict):
    edge_index = edge_index.get("edge_index", edge_index)
print(f"[✓] Edge index loaded: shape={edge_index.shape}, edges={edge_index.shape[1]}")

# 4. Load scaler
scaler_path = os.path.join(MODEL_DIR, "vayu_scaler.json")
with open(scaler_path) as f:
    scaler = json.load(f)
print(f"[✓] Scaler loaded: {len(scaler['features'])} features: {scaler['features']}")

# 5. Build dummy input tensor [1, 24, 250, 7]
dummy_input = torch.randn(1, 24, 250, 7)
print(f"\n[*] Running forward pass with input shape: {dummy_input.shape}")

with torch.no_grad():
    output = model(dummy_input, edge_index)

print(f"[✓] Output shape: {output.shape}")
assert output.shape == (1, 250, 5), f"FAIL: Expected (1, 250, 5), got {output.shape}"
print(f"\n{'=' * 60}")
print(f"  ALL TESTS PASSED ✓")
print(f"  Input:  [1, 24, 250, 7] → Output: [1, 250, 5]")
print(f"{'=' * 60}")
