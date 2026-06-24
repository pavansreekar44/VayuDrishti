import pandas as pd
import numpy as np
import torch
import math

# ==========================================
# CONFIGURATION
# ==========================================
INPUT_FILE = "master_delhi_aqi_5yr.csv"
FINAL_OUTPUT_FILE = "final_graph_delhi_aqi_5yr.csv"
EDGE_INDEX_FILE = "delhi_8km_edge_index.pt"

# Delhi City Center Coordinates (Connaught Place / India Gate area)
DELHI_CENTER_LAT = 28.6139
DELHI_CENTER_LON = 77.2090

# The maximum distance for stations to share an edge (in kilometers)
RADIUS_THRESHOLD_KM = 8.0

# NOTE: Replace this dictionary with the exact coordinates from your stations.py
# Ensure the keys EXACTLY match the 'Station_ID' names from your terminal output!
STATION_COORDS = {
    "Alipur": [28.815329, 77.15301],
    "Anand Vihar": [28.646835, 77.316032],
    "Ashok Vihar": [28.695381, 77.181665],
    "Bawana": [28.7762, 77.051074],
    "Cantonment Area": [28.5913, 77.1355],
    "Chandni Chowk": [28.656756, 77.227234],
    "Commonwealth Sports Complex": [28.6136, 77.2758],
    "DTU": [28.75005, 77.1112615],
    "Dr. Karni Singh Shooting Range": [28.498571, 77.26484],
    "Dwarka-Sector 8": [28.5710274, 77.0719006],
    "IGNOU Maidan Garhi": [28.4975, 77.2026],
    "IHBAS Dilshad Garden": [28.6821, 77.305],
    "IIT Delhi": [28.5448, 77.1923],
   # "IMD Lodhi Road": [28.588, 77.2215],# This station has no data

    "ITO": [28.628624, 77.24106],
    "JNU": [28.5398, 77.1654],
    "Jahangirpuri": [28.73282, 77.170633],
    "Jawaharlal Nehru Stadium": [28.58028, 77.233829],
    "Lodhi Road": [28.588333, 77.221667],
    "Major Dhyan Chand National Stadium": [28.611281, 77.237738],
    "Mandir Marg": [28.6341, 77.2005],
    "Mundka": [28.684678, 77.076574],
    "NSIT Dwarka": [28.60909, 77.0325413],
    "NSUT Jaffarpur": [28.6041, 76.9029],
    "Najafgarh": [28.570173, 76.933762],
    "Narela": [28.822836, 77.101981],
    "Nehru Nagar": [28.56789, 77.250515],
    "Okhla Phase-2": [28.530785, 77.271255],
    "Patparganj": [28.623748, 77.287205],
    "Punjabi Bagh": [28.674045, 77.131023],
    "Pusa": [28.639645, 77.146262],
    "R K Puram": [28.563262, 77.186937],
    "Rohini": [28.732528, 77.11992],
    "Shadipur": [28.6514781, 77.1473105],
    "Siri Fort": [28.5504249, 77.2159377],
    "Sonia Vihar": [28.710508, 77.249485],
    "Sri Aurobindo Marg": [28.531346, 77.190156],
    "Talkatora Garden": [28.6247, 77.1979],
    "Vivek Vihar": [28.672342, 77.31526],
    "Wazirpur": [28.699793, 77.165453]
}

def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculates distance between two coordinate points in kilometers."""
    R = 6371.0 # Earth radius in km
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = math.sin(dLat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dLon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def main():
    print("Loading Master Dataset...")
    df = pd.read_csv(INPUT_FILE)
    
    # 1. Map Coordinates
    print("Mapping geographic coordinates to stations...")
    df['Latitude'] = df['Station_ID'].map(lambda x: STATION_COORDS.get(x, [np.nan, np.nan])[0])
    df['Longitude'] = df['Station_ID'].map(lambda x: STATION_COORDS.get(x, [np.nan, np.nan])[1])
    
    if df['Latitude'].isna().any():
        print("WARNING: Some stations did not match the STATION_COORDS dictionary!")
        print("Missing:", df[df['Latitude'].isna()]['Station_ID'].unique())
        return

    # 2. Calculate Distance to Center (Feature 9)
    print("Calculating absolute distance to Delhi Center...")
    df['Dist_Center'] = df.apply(lambda row: haversine_distance(
        DELHI_CENTER_LAT, DELHI_CENTER_LON, row['Latitude'], row['Longitude']
    ), axis=1)
    
    # Save the final CSV
    print(f"Saving final graph-ready dataset to {FINAL_OUTPUT_FILE}...")
    df.to_csv(FINAL_OUTPUT_FILE, index=False)
    
    # ==========================================
    # GENERATE THE EDGE_INDEX TENSOR
    # ==========================================
    print("\nGenerating PyTorch Graph Topology (8km radius)...")
    
    # Create an ordered list of stations to define their numerical ID (0 to 38)
    station_names = sorted(list(STATION_COORDS.keys()))
    num_stations = len(station_names)
    
    edges_src = []
    edges_dst = []
    edge_weights = []
    
    for i in range(num_stations):
        for j in range(num_stations):
            if i != j:
                lat1, lon1 = STATION_COORDS[station_names[i]]
                lat2, lon2 = STATION_COORDS[station_names[j]]
                
                dist = haversine_distance(lat1, lon1, lat2, lon2)
                
                if dist <= RADIUS_THRESHOLD_KM:
                    edges_src.append(i)
                    edges_dst.append(j)
                    # Inverse distance weighting: Closer nodes have stronger bonds
                    edge_weights.append(1.0 / dist)
                    
    edge_index = torch.tensor([edges_src, edges_dst], dtype=torch.long)
    edge_attr = torch.tensor(edge_weights, dtype=torch.float32)
    
    print(f"Graph Topology Built: {edge_index.shape[1]} total edge connections found.")
    
    # Save the tensors so we can load them instantly in our PyTorch Dataset class
    torch.save({'edge_index': edge_index, 'edge_weight': edge_attr, 'station_order': station_names}, EDGE_INDEX_FILE)
    print(f"Saved PyTorch topology to {EDGE_INDEX_FILE}")
    print("✅ Phase 2 Complete!")

if __name__ == "__main__":
    main()