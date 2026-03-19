import json
import math

wards = [
    {"id": "W01", "name": "Connaught Place", "lat": 28.6315, "lon": 77.2167},
    {"id": "W02", "name": "Karol Bagh", "lat": 28.6519, "lon": 77.1888},
    {"id": "W03", "name": "Chanakyapuri", "lat": 28.5950, "lon": 77.1895},
    {"id": "W04", "name": "Dwarka", "lat": 28.5823, "lon": 77.0500},
    {"id": "W05", "name": "Chandni Chowk", "lat": 28.6505, "lon": 77.2303},
    {"id": "W06", "name": "Anand Vihar", "lat": 28.6489, "lon": 77.3152},
    {"id": "W07", "name": "Okhla", "lat": 28.5606, "lon": 77.2910},
    {"id": "W08", "name": "Najafgarh", "lat": 28.6090, "lon": 76.9855},
    {"id": "W09", "name": "Rohini", "lat": 28.7306, "lon": 77.1009},
    {"id": "W10", "name": "Vasant Kunj", "lat": 28.5292, "lon": 77.1534},
]

features = []
radius = 0.025 
for w in wards:
    # Create octagon for each ward
    coords = []
    for i in range(9):
        angle = i * (2 * math.pi / 8)
        lat = w['lat'] + radius * math.cos(angle)
        lon = w['lon'] + radius * math.sin(angle)
        coords.append([lon, lat])
    
    features.append({
        "type": "Feature",
        "properties": {"id": w["id"], "name": w["name"], "rand_aqi": w['lat']},
        "geometry": {"type": "Polygon", "coordinates": [coords]}
    })

geojson = {"type": "FeatureCollection", "features": features}
with open('delhi_wards.geojson', 'w') as f:
    json.dump(geojson, f)
print("GeoJSON saved successfully!")
