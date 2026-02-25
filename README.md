# 🌫️ BreatheSafe — AI-Powered Clean Air Navigation

> **Hackathon Round 2 Submission** — Proof of Concept

BreatheSafe is a Spatio-Temporal Graph Neural Network routing system that helps citizens of Hyderabad navigate using the **cleanest air route**, not just the shortest one. It combines real-world OpenStreetMap road data, a trained **A3T-GCN (Attention Temporal Graph Convolutional Network)** AI model, and a live interactive map to show you two routes side-by-side: the fastest path vs. the lowest pollution exposure path.

---

## 🔬 How It Works

```
User Input (Start/End) 
    → FastAPI Backend 
    → OSMnx 60KM Road Graph (Hyderabad)
    → A* Spatio-Temporal Router [alpha·Distance + beta·PM2.5_Exposure]
    → A3T-GCN PyTorch Model (Predicts PM2.5 per road segment)
    → GeoJSON Routes returned
    → React + Leaflet Map (Dark Mode, Live heatmap overlay)
```

### The AI Model — A3T-GCN
- **Spatial:** Graph Convolutional Network learns which neighbouring intersections share pollution patterns
- **Temporal:** GRU (Gated Recurrent Unit) processes the last 24 hours of data
- **Attention:** Weights which past time-steps matter most for prediction
- **Trained on:** 14 days of synthesized PM2.5 data across 7,436 major intersections in Hyderabad (60km diameter)

---

## 🚀 Setup Instructions

### Prerequisites
- Python 3.10+
- Node.js 18+
- Git

### 1. Clone the Repository
```bash
git clone <your-repo-url>
cd iitbhu
```

### 2. Backend Setup
```bash
cd backend

# Create and activate virtual environment
python -m venv venv

# Windows
.\venv\Scripts\Activate.ps1
# Mac/Linux
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start the backend server
uvicorn app.main:app --port 8000 --reload
```

> ⚠️ **First Run Note:** On the very first startup, the backend will automatically download the Hyderabad city road map from OpenStreetMap (~2-3 minutes). This only happens once — subsequent starts load from local cache instantly.

### 3. Frontend Setup
```bash
cd web-frontend

# Install dependencies
npm install

# Start the development server
npm run dev
```

### 4. Open the App
Navigate to **http://localhost:5173** in your browser.

---

## 🗂️ Project Structure

```
iitbhu/
├── backend/
│   ├── app/
│   │   ├── ai/
│   │   │   ├── a3tgcn.py          # A3T-GCN PyTorch model architecture
│   │   │   ├── dataset.py         # PyTorch Geometric dataset loader
│   │   │   ├── train.py           # Model training loop
│   │   │   ├── inference.py       # Live PM2.5 prediction engine (singleton)
│   │   │   └── data_synthesis.py  # 60KM Hyderabad data generator
│   │   ├── api/
│   │   │   └── endpoints/
│   │   │       └── navigation.py  # FastAPI route endpoints + A* trigger
│   │   ├── services/
│   │   │   └── routing_engine.py  # Custom A* Spatio-Temporal Router
│   │   └── data/
│   │       ├── a3tgcn_weights.pt              # Trained PyTorch model
│   │       ├── synthetic_training_tensor.pkl  # Training dataset
│   │       └── hyderabad_60km_major.graphml   # 60KM road graph
│   └── requirements.txt
└── web-frontend/
    └── src/
        ├── App.tsx                # Root app, API calls
        └── components/
            ├── LeafletMap.tsx     # Interactive Leaflet dark-mode map
            └── MapControl.tsx     # Route controls + health slider
```

---

## 🎯 Key Features

| Feature | Description |
|---|---|
| 🗺️ **60KM City Map** | Full Hyderabad metropolitan road network |
| 🤖 **A3T-GCN AI** | Spatio-Temporal Graph Neural Network predicts PM2.5 per road |
| 🔴 **Fastest Route** | Standard shortest-path (red dashed line) |
| 🟢 **Cleanest Route** | Minimum pollution-exposure path (solid green line) |
| 🎚️ **Health Slider** | Tune the tradeoff between speed and clean air (0–100%) |
| 📊 **Route Stats** | Shows distance, exposure reduction %, and PM2.5 delta |
| 🌙 **Dark Map** | CARTO dark basemap for visibility |

---

## 🧪 Running the AI Training (Optional)

The trained weights are already included. To retrain:

```bash
cd backend

# Step 1: Generate 60KM dataset (takes ~5 min)
python -m app.ai.data_synthesis

# Step 2: Train the A3T-GCN model
python -m app.ai.train
```

---

## 📦 Tech Stack

**Backend:** Python, FastAPI, Uvicorn, OSMnx, NetworkX, PyTorch, PyTorch Geometric  
**Frontend:** React, TypeScript, Vite, Leaflet, react-leaflet  
**AI Model:** A3T-GCN (Attention Temporal Graph Convolutional Network)  
**Data:** OpenStreetMap (OSMnx), Synthesized PM2.5 temporal data

---

## 👥 Team
IIT BHU Hackathon Team
