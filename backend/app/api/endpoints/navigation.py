from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Dict, Any
import networkx as nx
from app.services.routing_engine import AStarSpatioTemporalRouter

router = APIRouter()

class NavigationResponse(BaseModel):
    shortest_path_geojson: Dict[str, Any]
    cleanest_path_geojson: Dict[str, Any]
    stats: Dict[str, float]

def convert_path_to_geojson(G: nx.MultiDiGraph, path: List[Any], name: str, color: str) -> Dict[str, Any]:
    """Helper formatting the output path into Mapbox compatible GeoJSON."""
    coordinates = []
    
    if len(path) > 1:
        for i in range(len(path) - 1):
            u = path[i]
            v = path[i+1]
            edge_data = G.get_edge_data(u, v)
            
            if edge_data and 0 in edge_data:
                edge = edge_data[0]
                if 'geometry' in edge:
                    # 'geometry' contains the true curved linestring from OSM
                    for lon, lat in edge['geometry'].coords:
                        if not coordinates or coordinates[-1] != [lon, lat]:
                            coordinates.append([lon, lat])
                else:
                    # Fallback to straight line between nodes if no curve exists
                    u_node = G.nodes[u]
                    v_node = G.nodes[v]
                    if not coordinates or coordinates[-1] != [u_node['x'], u_node['y']]:
                        coordinates.append([u_node['x'], u_node['y']])
                    coordinates.append([v_node['x'], v_node['y']])
    elif len(path) == 1:
        n = G.nodes[path[0]]
        coordinates.extend([[n['x'], n['y']], [n['x'], n['y']]])

    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "name": name,
                    "color": color
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": coordinates
                }
            }
        ]
    }

import os
import osmnx as ox

# Create a data directory for the cached map
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

GRAPH_FILE = os.path.join(DATA_DIR, "hyderabad_cached.graphml")
G_GLOBAL = None

import math

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000 # radius of Earth in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def get_global_graph():
    global G_GLOBAL
    if G_GLOBAL is not None:
        return G_GLOBAL
        
    print("Initializing Global Map Cache...")
    if os.path.exists(GRAPH_FILE):
        print(f"Loading city map from local cache: {GRAPH_FILE}")
        G_GLOBAL = ox.load_graphml(GRAPH_FILE)
    else:
        print("Downloading single-city map from OSM (This only happens once!)...")
        # Use a safe 8km radius (16km diameter, ~200 sq km) to avoid Python RAM Exhaustion
        center_point = (17.4239, 78.4738)
        G_GLOBAL = ox.graph_from_point(center_point, dist=8000, network_type='drive', simplify=True)
        
        for u, v, key, data in G_GLOBAL.edges(keys=True, data=True):
            if 'length' not in data:
                data['length'] = 10.0
            data['aspect_ratio'] = 0.8
            data['svf'] = 0.5
            
        print(f"Saving city map to local cache: {GRAPH_FILE}")
        ox.save_graphml(G_GLOBAL, GRAPH_FILE)
        
    return G_GLOBAL

@router.get("/route", response_model=NavigationResponse)
async def get_optimal_route(
    start_lat: float = Query(..., description="Starting node latitude"),
    start_lon: float = Query(..., description="Starting node longitude"),
    end_lat: float = Query(..., description="Destination node latitude"),
    end_lon: float = Query(..., description="Destination node longitude"),
    health_sensitivity: int = Query(50, ge=0, le=100, description="0 (Distance only) to 100 (Cleanest air only)")
):
    """
    Computes and compares the default shortest geographic path against
    the Spatio-Temporal Clean-Air route using a globally cached map to ensure millisecond latency.
    """
    try:
        # 1. Fetch cached Real City Street Network
        G = get_global_graph()

        # Snap coordinates to the nearest valid intersection nodes
        source_node = ox.distance.nearest_nodes(G, start_lon, start_lat)
        target_node = ox.distance.nearest_nodes(G, end_lon, end_lat)
        
        # Verify the requested GPS coordinates actually exist within our cached city network
        slat, slon = G.nodes[source_node]['y'], G.nodes[source_node]['x']
        tlat, tlon = G.nodes[target_node]['y'], G.nodes[target_node]['x']
        
        dist_start = haversine(start_lat, start_lon, slat, slon)
        dist_end = haversine(end_lat, end_lon, tlat, tlon)
        
        if dist_start > 8000 or dist_end > 8000:
            raise HTTPException(
                status_code=400, 
                detail=f"Addresses are outside the cached Hyderabad city limits. Start snapped by {int(dist_start)}m, End by {int(dist_end)}m. Please choose locations closer to the center (e.g., Banjara Hills, Secunderabad, Begumpet, Uppal)."
            )
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load city infrastructure from cache: {str(e)}")
    
    # 2. Initialize Router
    engine = AStarSpatioTemporalRouter(G)
    
    try:
        print(f"Starting A* Route calculation from node {source_node} to {target_node}...")
        
        # 3. Compute Shortest Path (beta = 0.0)
        print("[1/2] Calculating absolute Shortest Geographic Path...")
        path_s, dist_s, exp_s = engine.compute_route(source_node, target_node, beta=0.0)
        
        # 4. Compute Cleanest Path (beta dynamically mapped: 0 -> 0.0, 100 -> 1.0)
        print(f"[2/2] Calculating Cleanest Air Path (Health Sensitivity Beta: {health_sensitivity}%)...")
        beta_val = health_sensitivity / 100.0
        path_c, dist_c, exp_c = engine.compute_route(source_node, target_node, beta=beta_val)
        
        print("Success! Both routes compiled. Formatting GeoJSON...")
        
    except nx.NetworkXNoPath:
        print("A* Error: No feasible route between nodes!")
        raise HTTPException(status_code=404, detail="No feasible route found between coordinates.")
        
    # 5. Compile Statistics
    exposure_diff = exp_s - exp_c
    exposure_pct_reduction = (exposure_diff / exp_s * 100) if exp_s > 0 else 0
    
    distance_diff = dist_c - dist_s
    distance_pct_increase = (distance_diff / dist_s * 100) if dist_s > 0 else 0
            
    stats = {
        "shortest_dist_m": dist_s,
        "cleanest_dist_m": dist_c,
        "fastest_pm25_exposure": exp_s,
        "cleanest_pm25_exposure": exp_c,
        "exposure_reduction_pct": exposure_pct_reduction,
        "distance_increase_pct": distance_pct_increase
    }
    
    # 6. Build GeoJSON Maps
    gj_short = convert_path_to_geojson(G, path_s, "Shortest Route", "#FF0000")
    gj_clean = convert_path_to_geojson(G, path_c, "Clean Air Route", "#00FF00")

    return NavigationResponse(
        shortest_path_geojson=gj_short,
        cleanest_path_geojson=gj_clean,
        stats=stats
    )
