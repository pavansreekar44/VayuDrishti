import os
import networkx as nx
import numpy as np
import pickle
import osmnx as ox
import time

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
GRAPH_FILE = os.path.join(DATA_DIR, "hyderabad_60km_major.graphml")

def generate_60km_filtered_graph():
    """
    Downloads ONLY major highways/trunks for a 60km diameter Hyderabad to keep RAM usage low.
    """
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
        
    print(f"Creating highly-filtered 60km (30km radius) Regional Map...")
    
    # Filter to ignore millions of residential alleys
    custom_filter = '["highway"~"motorway|motorway_link|trunk|trunk_link|primary|primary_link|secondary|secondary_link"]'
    
    start_time = time.time()
    # 30000m radius = 60km diameter spanning the entire metropolitan area
    center_point = (17.4239, 78.4738)
    G = ox.graph_from_point(
        center_point, 
        dist=30000, 
        custom_filter=custom_filter, 
        simplify=True
    )
    
    print(f"Download complete! Found {len(G.nodes)} major intersections across 60km region.")
    print(f"Completed in {int(time.time() - start_time)} seconds.")
    
    # Impute missing attributes
    for u, v, key, data in G.edges(keys=True, data=True):
        if 'length' not in data:
            data['length'] = 100.0
            
    ox.save_graphml(G, GRAPH_FILE)
    return G

def synthesize_temporal_data(G, days=7):
    """
    Simulates coherent temporal PM2.5 readings for every node across a timeframe,
    injecting specific rush hour "traffic pulses" on major highways.
    """
    print(f"Synthesizing {days} days of historical 1-hour temporal pollution data...")
    
    num_nodes = len(G.nodes)
    seq_len = days * 24 # 168 hours
    
    # Build a stable adjacency map for continuous mapping
    node_mapping = {old_id: new_id for new_id, old_id in enumerate(G.nodes())}
    
    # Features matrix: [Node, Time, Features] -> [N, T, 5]
    # Features = [PM2.5, PM10, NO2, Temperature, Traffic_Intensity]
    X_tensor = np.zeros((num_nodes, seq_len, 5), dtype=np.float32)
    Y_tensor = np.zeros((num_nodes, seq_len, 1), dtype=np.float32) # Target is PM2.5 at t+1
    
    for t in range(seq_len):
        hour_of_day = t % 24
        
        # Rush hour peak multipliers (8 AM and 6 PM)
        rush_hour_mult = 1.0
        if 7 <= hour_of_day <= 10:
            rush_hour_mult = 2.5
        elif 17 <= hour_of_day <= 20:
            rush_hour_mult = 3.0
        elif 0 <= hour_of_day <= 5:
            rush_hour_mult = 0.4 # Quiet night
            
        # Global daily weather drift (sine wave over 7 days)
        weather_drift = np.sin((t / seq_len) * np.pi * 2) * 15.0
            
        for node_id, data in G.nodes(data=True):
            idx = node_mapping[node_id]
            
            # Base logic: Central nodes (near Hussain sagar) are generally more polluted
            # We'll use coordinate distance to center as a natural bias
            center_lat, center_lon = 17.4239, 78.4738
            node_lat, node_lon = data.get('y', center_lat), data.get('x', center_lon)
            
            # Rough proxy for "downtown" proximity
            dist_to_center = np.sqrt((node_lat - center_lat)**2 + (node_lon - center_lon)**2)
            urban_density_mult = max(0.5, 2.0 - (dist_to_center * 10))
            
            # Synthesize Base PM2.5 (Realistic Indian Metro levels: 40 to 180)
            base_pm25 = 45.0
            node_noise = np.random.normal(0, 5)
            
            current_pm25 = base_pm25 * urban_density_mult * rush_hour_mult + weather_drift + node_noise
            current_pm25 = max(5.0, min(current_pm25, 400.0)) # clip to valid AQI range
            
            # Additional features
            pm10 = current_pm25 * 1.5 + np.random.normal(0, 10)
            no2 = current_pm25 * 0.4 * rush_hour_mult
            temp = 25.0 + np.sin((hour_of_day - 6) / 24 * np.pi * 2) * 8.0
            traffic = 100 * rush_hour_mult * urban_density_mult
            
            X_tensor[idx, t] = [current_pm25, pm10, no2, temp, traffic]
            
            # For supervised learning, the "Y" label at time t is actually the PM2.5 reading at time t+1
            # We will shift this at the end
            Y_tensor[idx, t] = [current_pm25]
            
        if t % 24 == 0:
            print(f"Synthesized Day {t//24 + 1}/{days}...")

    # Shift Y tensor by 1 time step to create the forecasting target (Predicting t+1)
    Y_shifted = np.zeros_like(Y_tensor)
    Y_shifted[:, :-1, :] = Y_tensor[:, 1:, :]
    Y_shifted[:, -1, :] = Y_tensor[:, -1, :] # Last timestep copies itself as padding
    
    print("Saving Tensor Dumps for PyTorch...")
    dataset = {
        'x': X_tensor,
        'y': Y_shifted,
        'node_mapping': node_mapping,
        'edge_index': list(G.edges(keys=False))
    }
    
    with open(os.path.join(DATA_DIR, 'synthetic_training_tensor.pkl'), 'wb') as f:
        pickle.dump(dataset, f)
        
    print("Process Complete! Ready for A3T-GCN Training.")

if __name__ == "__main__":
    G = generate_60km_filtered_graph()
    synthesize_temporal_data(G, days=14) # Gen 2 weeks of data
