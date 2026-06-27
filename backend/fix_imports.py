import os
import re

endpoints_dir = "app/api/endpoints"
for filename in os.listdir(endpoints_dir):
    if not filename.endswith(".py"): continue
    path = os.path.join(endpoints_dir, filename)
    with open(path, "r") as f:
        content = f.read()
    
    changed = False
    
    if "INFERENCE_GRID_CACHE" in content:
        content = content.replace(
            "from app.api.endpoints.dashboard import INFERENCE_GRID_CACHE, fetch_openaq_station_anchors",
            "from app.services.ml_engine import ML_ENGINE"
        )
        content = content.replace(
            "from app.api.endpoints.dashboard import INFERENCE_GRID_CACHE",
            "from app.services.ml_engine import ML_ENGINE"
        )
        content = content.replace(
            "INFERENCE_GRID_CACHE.get(\"data\", [])",
            "list(ML_ENGINE.get_cached_predictions()[0].values()) if ML_ENGINE.get_cached_predictions()[0] else []"
        )
        content = content.replace(
            "INFERENCE_GRID_CACHE.get(\"data\")",
            "ML_ENGINE.get_cached_predictions()[0]"
        )
        changed = True
        
    if changed:
        with open(path, "w") as f:
            f.write(content)
        print(f"Fixed {filename}")

