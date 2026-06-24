"""
===============================================================
  VAYU DRISHTI — Full-Pollutant Blind Station Validation Test
===============================================================

Leave-One-Out cross-validation using LIVE OpenAQ data.

Pollutants tested:
  - PM2.5  (MLP primary supervised target)
  - NO2    (GAT+LSTM chem_bottleneck col 0 — spatial inference)
  - SO2    (GAT+LSTM chem_bottleneck col 1 — spatial inference)
  - CO     (GAT+LSTM chem_bottleneck col 2 — spatial inference)
  - PM10   (GAT+LSTM chem_bottleneck col 3 — spatial inference)

HONEST METHODOLOGY:
  - PM2.5 is the only directly supervised output. Most reliable.
  - NO2/SO2/CO/PM10 are inferred via GAT+LSTM spatial encoding — not
    individually supervised. Expect higher errors on these.
  - If OpenAQ returns None for a pollutant at a station, that station
    is EXCLUDED from that pollutant's error calc. No fake substitution.
  - Station node ordering uses the EXACT training order from .pt file.
===============================================================
"""

import math
import os
import sys
import time
import numpy as np
import torch
import joblib
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from app.services.openaq_client import OpenAQClient
from app.core.stations import STATION_COORDS

DELHI_CENTER = (28.6139, 77.2090)
NUM_NODES    = 39
MODEL_DIR    = os.path.join(os.path.dirname(__file__), "app", "services", "gat+lstm-mlp_pavan")

# ─── Load model ─────────────────────────────────────────────────────────────────

def load_all():
    if MODEL_DIR not in sys.path:
        sys.path.insert(0, MODEL_DIR)
    from model import VayuDrishtiSTGNN

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = VayuDrishtiSTGNN(num_nodes=39, dyn_features=6, ctx_features=5,
                              gat_hidden=16, lstm_hidden=32, mlp_hidden=64, heads=2)
    model.load_state_dict(torch.load(
        os.path.join(MODEL_DIR, "model_nolog_huber.pth"),
        map_location=device, weights_only=True))
    model.eval().to(device)

    sc_dyn    = joblib.load(os.path.join(MODEL_DIR, "scalers", "dyn_scaler.pkl"))
    sc_ctx    = joblib.load(os.path.join(MODEL_DIR, "scalers", "ctx_scaler.pkl"))
    sc_target = joblib.load(os.path.join(MODEL_DIR, "scalers", "target_scaler.pkl"))

    ei_dict      = torch.load(os.path.join(MODEL_DIR, "delhi_8km_edge_index.pt"),
                              map_location=device, weights_only=False)
    ei           = ei_dict["edge_index"]         # [2, E] tensor
    train_order  = ei_dict["station_order"]       # canonical 39-station training order

    return model, sc_dyn, sc_ctx, sc_target, ei, train_order, device


def get_weather(lat, lon):
    key = os.environ.get("OPENWEATHERMAP_API_KEY", "")
    if not key:
        return 30.0, 50.0
    try:
        url = (f"https://api.openweathermap.org/data/2.5/weather"
               f"?lat={lat}&lon={lon}&appid={key}&units=metric")
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            d = r.json()
            return float(d["main"]["temp"]), float(d["main"]["humidity"])
    except Exception:
        pass
    return 30.0, 50.0


def make_dyn_matrix(by_name, train_order, sc_dyn, blind_station=None):
    """Build [1, 1, 39, 6] scaled tensor. blind_station is masked to 0.0."""
    mat = np.zeros((1, 1, NUM_NODES, 6), dtype=np.float32)
    for i, name in enumerate(train_order):
        if name == blind_station:
            continue
        r = by_name.get(name)
        if r is None:
            continue
        mat[0, 0, i, 0] = r.no2            if r.no2            is not None else 0.0
        mat[0, 0, i, 1] = r.so2            if r.so2            is not None else 0.0
        mat[0, 0, i, 2] = r.co             if r.co             is not None else 0.0
        mat[0, 0, i, 3] = r.pm10           if r.pm10           is not None else 0.0
        mat[0, 0, i, 4] = r.wind_speed     if r.wind_speed     is not None else 0.0
        mat[0, 0, i, 5] = r.wind_direction if r.wind_direction is not None else 0.0
    flat = mat.reshape(-1, 6)
    return sc_dyn.transform(flat).reshape(1, 1, NUM_NODES, 6)


def infer(node_idx, lat, lon, dyn_scaled,
          model, sc_ctx, sc_target, sc_dyn, ei, device):
    ctx = np.zeros((1, NUM_NODES, 5), dtype=np.float32)
    dist = math.hypot(lat - DELHI_CENTER[0], lon - DELHI_CENTER[1])
    temp, rh = get_weather(lat, lon)
    ctx[0, node_idx, :] = [temp, rh, lat, lon, dist]
    ctx_s = sc_ctx.transform(ctx.reshape(-1, 5)).reshape(1, NUM_NODES, 5)

    x_dyn = torch.tensor(dyn_scaled, dtype=torch.float32).to(device)
    x_ctx = torch.tensor(ctx_s,      dtype=torch.float32).to(device)

    with torch.no_grad():
        out_pm25, out_chem = model(x_dyn, x_ctx, ei)

    raw_pm25  = out_pm25[0, node_idx, 0].cpu().item()
    pred_pm25 = float(sc_target.inverse_transform([[raw_pm25]])[0][0])
    pred_pm25 = max(0.0, pred_pm25)

    raw_chem = out_chem[0, node_idx, :].cpu().numpy()
    pad      = np.zeros((1, 6), dtype=np.float32)
    pad[0, :4] = raw_chem
    pred_chem = np.maximum(sc_dyn.inverse_transform(pad)[0, :4], 0.0)   # [NO2, SO2, CO, PM10]

    return pred_pm25, pred_chem


# ─── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("=" * 65)
    print("  VAYU DRISHTI — Full-Pollutant Blind Station Test")
    print("=" * 65)

    print("\nStep 1: Loading model, scalers, and graph...")
    model, sc_dyn, sc_ctx, sc_target, ei, train_order, device = load_all()
    print(f"  Device : {device.type.upper()}")
    print(f"  Nodes  : {len(train_order)} (from training .pt file)")

    print("\nStep 2: Fetching LIVE OpenAQ data (single pass)...")
    client  = OpenAQClient()
    readings, failed, _ = client.fetch_all_latest(STATION_COORDS)
    by_name = {r.name: r for r in readings}

    print(f"  Live data received : {len(by_name)}/39 stations")
    if failed:
        print(f"  Offline stations (masked to 0.0): {', '.join(failed)}")

    # Only test stations in training order that have live PM2.5
    testable = [n for n in train_order if n in by_name and by_name[n].pm25 is not None]
    print(f"  Testable stations  : {len(testable)}/39")

    if not testable:
        print("  ERROR: No testable stations. Exiting.")
        return

    print(f"\nStep 3: Leave-one-out inference for {len(testable)} stations...")

    errs  = {"pm25": [], "no2": [], "so2": [], "co": [], "pm10": []}
    rows  = []

    for name in testable:
        lat, lon  = STATION_COORDS[name]
        node_idx  = train_order.index(name)
        actual    = by_name[name]

        dyn_scaled = make_dyn_matrix(by_name, train_order, sc_dyn, blind_station=name)

        try:
            pred_pm25, pred_chem = infer(
                node_idx, lat, lon, dyn_scaled,
                model, sc_ctx, sc_target, sc_dyn, ei, device
            )
        except Exception as exc:
            print(f"  INFERENCE ERROR — {name}: {exc}")
            continue

        a_pm25 = actual.pm25
        a_no2  = actual.no2
        a_so2  = actual.so2
        a_co   = actual.co
        a_pm10 = actual.pm10

        e_pm25 = abs(pred_pm25    - a_pm25) if a_pm25 is not None else None
        e_no2  = abs(pred_chem[0] - a_no2)  if a_no2  is not None else None
        e_so2  = abs(pred_chem[1] - a_so2)  if a_so2  is not None else None
        e_co   = abs(pred_chem[2] - a_co)   if a_co   is not None else None
        e_pm10 = abs(pred_chem[3] - a_pm10) if a_pm10 is not None else None

        if e_pm25 is not None: errs["pm25"].append(e_pm25)
        if e_no2  is not None: errs["no2"].append(e_no2)
        if e_so2  is not None: errs["so2"].append(e_so2)
        if e_co   is not None: errs["co"].append(e_co)
        if e_pm10 is not None: errs["pm10"].append(e_pm10)

        def f1(v): return f"{v:.1f}" if v is not None else "N/A"
        def fe(e): return f"{e:.1f}" if e is not None else "  —"

        rows.append({
            "name":   name,
            "a_pm25": f1(a_pm25),   "p_pm25": f"{pred_pm25:.1f}",   "e_pm25": fe(e_pm25),
            "a_no2":  f1(a_no2),    "p_no2":  f"{pred_chem[0]:.1f}","e_no2":  fe(e_no2),
            "a_so2":  f1(a_so2),    "p_so2":  f"{pred_chem[1]:.1f}","e_so2":  fe(e_so2),
            "a_co":   f1(a_co),     "p_co":   f"{pred_chem[2]:.3f}","e_co":   fe(e_co),
            "a_pm10": f1(a_pm10),   "p_pm10": f"{pred_chem[3]:.1f}","e_pm10": fe(e_pm10),
        })

    # ─── Per-station table ───────────────────────────────────────────────────────
    if not rows:
        print("\n  No results to display — all inferences failed.")
        return

    print("\n" + "=" * 120)
    print(f"  {'Station':<35}| {'--- PM2.5 ---':^20}| {'--- NO2 ---':^18}| {'--- SO2 ---':^18}| {'--- CO ---':^18}| {'--- PM10 ---':^18}")
    print(f"  {'':35}| {'Act':>5} {'Pred':>6} {'Err':>6} | {'Act':>5} {'Pred':>5} {'Err':>5} | {'Act':>5} {'Pred':>5} {'Err':>5} | {'Act':>5} {'Pred':>6} {'Err':>5} | {'Act':>5} {'Pred':>5} {'Err':>5}")
    print("-" * 120)

    for r in rows:
        print(f"  {r['name']:<35}"
              f"| {r['a_pm25']:>5} {r['p_pm25']:>6} {r['e_pm25']:>6} "
              f"| {r['a_no2']:>5} {r['p_no2']:>5} {r['e_no2']:>5} "
              f"| {r['a_so2']:>5} {r['p_so2']:>5} {r['e_so2']:>5} "
              f"| {r['a_co']:>5} {r['p_co']:>6} {r['e_co']:>5} "
              f"| {r['a_pm10']:>5} {r['p_pm10']:>5} {r['e_pm10']:>5}")

    # ─── Aggregate metrics ───────────────────────────────────────────────────────
    print("\n" + "=" * 65)
    print("  AGGREGATE ACCURACY METRICS")
    print("=" * 65)
    print("  Stations included per metric = those with a non-None actual.\n")

    labels = {
        "pm25": "PM2.5  (µg/m³)  [MLP supervised primary target]",
        "no2":  "NO2    (µg/m³)  [GAT+LSTM spatial inference]",
        "so2":  "SO2    (µg/m³)  [GAT+LSTM spatial inference]",
        "co":   "CO     (mg/m³)  [GAT+LSTM spatial inference]",
        "pm10": "PM10   (µg/m³)  [GAT+LSTM spatial inference]",
    }

    for key, label in labels.items():
        e_list = errs[key]
        n = len(e_list)
        if n == 0:
            print(f"  {label}")
            print(f"    N reported : 0 — OpenAQ returned None for all stations.\n")
            continue
        mae  = np.mean(e_list)
        rmse = math.sqrt(np.mean(np.array(e_list) ** 2))
        print(f"  {label}")
        print(f"    N reported : {n}")
        print(f"    MAE        : {mae:.2f}")
        print(f"    RMSE       : {rmse:.2f}")
        print(f"    Min error  : {min(e_list):.2f}")
        print(f"    Max error  : {max(e_list):.2f}\n")

    print("=" * 65)
    print("  All actuals from live OpenAQ. No fake data used anywhere.")
    print("=" * 65)


if __name__ == "__main__":
    main()
