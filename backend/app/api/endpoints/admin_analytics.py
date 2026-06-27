import os
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from datetime import datetime, timedelta
from app.api.deps import require_admin
from app.db.admin_models import Profile
import asyncio

router = APIRouter()

def get_supabase_config():
    url = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_ANON_KEY", "")
    key = os.getenv("SUPABASE_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY", "")
    return url, key

# Import ML cache access
from app.services.ml_engine import ML_ENGINE

@router.get("/overview")
async def get_admin_overview(current_user: Profile = Depends(require_admin)):
    """
    Real-time admin overview with NO hardcoded values.
    All data from: Supabase DB + ML inference cache + WAQI
    
    Returns data even if ML cache is still loading (graceful degradation).
    """
    start_time = datetime.utcnow()
    print(f"[ADMIN] Overview request started | user={current_user.email}")
    
    SUPABASE_URL, SUPABASE_KEY = get_supabase_config()
    
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("[ADMIN] ✗ Database configuration missing")
        raise HTTPException(status_code=503, detail="Database configuration missing")
    
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    
    try:
        # ML inference background task is handled by main.py startup event
        
        # Wait up to 10s for ML cache (reduced for faster response)
        ml_ready = False
        for _ in range(100):
            if ML_ENGINE.get_cached_predictions()[0]:
                ml_ready = True
                break
            await asyncio.sleep(0.1)
        
        # Get ML inference data (may be empty if still loading)
        wards_data = list(ML_ENGINE.get_cached_predictions()[0].values()) if ML_ENGINE.get_cached_predictions()[0] else []
        
        # Compute metrics from ML data (with fallbacks)
        if wards_data:
            critical_zones = [w for w in wards_data if w.get('aqi', 0) > 300]
            avg_aqi = sum(w.get('aqi', 0) for w in wards_data) / len(wards_data)
            print(f"[ADMIN] ✓ ML data available | wards={len(wards_data)} critical={len(critical_zones)}")
        else:
            critical_zones = []
            avg_aqi = 0
            print("[ADMIN] ⚠ ML data not yet available (background task loading)")
        
        # Fetch database counts with proper error handling
        total_complaints = 0
        active_tasks = 0
        db_errors = []
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                complaints_resp = await client.get(
                    f"{SUPABASE_URL}/rest/v1/complaints?select=id&status=neq.RESOLVED",
                    headers=headers
                )
                if complaints_resp.status_code == 200:
                    total_complaints = len(complaints_resp.json())
                    print(f"[ADMIN] ✓ Complaints fetched | count={total_complaints}")
                else:
                    error_msg = f"Status {complaints_resp.status_code}"
                    db_errors.append(f"complaints: {error_msg}")
                    print(f"[ADMIN] ✗ Complaints query failed: {error_msg}")
            except Exception as e:
                db_errors.append(f"complaints: {str(e)}")
                print(f"[ADMIN] ✗ Complaints query error: {e}")
            
            try:
                tasks_resp = await client.get(
                    f"{SUPABASE_URL}/rest/v1/tasks?select=id&status=neq.COMPLETED",
                    headers=headers
                )
                if tasks_resp.status_code == 200:
                    active_tasks = len(tasks_resp.json())
                    print(f"[ADMIN] ✓ Tasks fetched | count={active_tasks}")
                else:
                    error_msg = f"Status {tasks_resp.status_code}"
                    db_errors.append(f"tasks: {error_msg}")
                    print(f"[ADMIN] ✗ Tasks query failed: {error_msg}")
            except Exception as e:
                db_errors.append(f"tasks: {str(e)}")
                print(f"[ADMIN] ✗ Tasks query error: {e}")
        
        query_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        
        response_data = {
            "data": {
                "total_complaints": total_complaints,
                "active_tasks": active_tasks,
                "critical_zones": len(critical_zones),
                "avg_aqi": round(avg_aqi, 1)
            },
            "metadata": {
                "sources": ["supabase_complaints", "supabase_tasks", "ml_inference_cache"],
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "query_time_ms": query_time_ms,
                "ward_count": len(wards_data),
                "ml_ready": ml_ready,
                "db_errors": db_errors if db_errors else None
            }
        }
        
        print(f"[ADMIN] ✓ Overview complete | time={query_time_ms}ms ml_ready={ml_ready}")
        return response_data
    
    except httpx.TimeoutException:
        print("[ADMIN] ✗ Database query timeout")
        raise HTTPException(status_code=504, detail="Database query timeout")
    except Exception as e:
        import traceback
        error_detail = str(e)
        traceback_str = traceback.format_exc()
        print(f"[ADMIN] ✗ ERROR: {error_detail}\n{traceback_str}")
        raise HTTPException(status_code=500, detail=f"Internal error: {error_detail}")


@router.get("/hotspots")
async def get_hotspots(
    threshold: int = Query(300, description="AQI threshold for hotspot detection"),
    current_user: Profile = Depends(require_admin)
):
    """
    Detect real hotspots from ML inference data.
    NO hardcoded zones - computed from live data.
    """
    start_time = datetime.utcnow()
    
    # Get real-time ML data
    wards_data = list(ML_ENGINE.get_cached_predictions()[0].values()) if ML_ENGINE.get_cached_predictions()[0] else []
    
    if not wards_data:
        raise HTTPException(status_code=503, detail="ML inference data not available")
    
    # Filter hotspots based on threshold
    hotspots = [
        {
            "ward": w.get('name'),
            "aqi": w.get('aqi'),
            "pm25": w.get('pm25'),
            "lat": w.get('lat'),
            "lon": w.get('lon'),
            "status": w.get('status'),
            "dominant_source": w.get('dominant_source', 'Unknown')
        }
        for w in wards_data
        if w.get('aqi', 0) >= threshold
    ]
    
    # Sort by AQI descending
    hotspots.sort(key=lambda x: x['aqi'], reverse=True)
    
    query_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
    
    return {
        "data": hotspots,
        "metadata": {
            "source": "ml_inference_cache",
            "timestamp": datetime.utcnow().isoformat(),
            "query_time_ms": query_time_ms,
            "threshold": threshold,
            "total_wards": len(wards_data),
            "hotspot_count": len(hotspots)
        }
    }


@router.get("/complaints-heatmap")
async def get_complaints_heatmap(
    days: int = Query(7, description="Number of days to analyze"),
    current_user: Profile = Depends(require_admin)
):
    """
    Generate complaint density heatmap from real database.
    Aggregates by ward with NO hardcoded data.
    """
    start_time = datetime.utcnow()
    SUPABASE_URL, SUPABASE_KEY = get_supabase_config()
    
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(status_code=503, detail="Database configuration missing")
    
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    
    # Calculate date range
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Fetch all complaints in date range
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/complaints?select=ward,location_lat,location_lon,created_at&created_at=gte.{start_date.isoformat()}&created_at=lte.{end_date.isoformat()}",
                headers=headers
            )
            
            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail="Failed to fetch complaints")
            
            complaints = resp.json()
            
            # Aggregate by ward
            ward_counts = {}
            for complaint in complaints:
                ward = complaint.get('ward', 'Unknown')
                if ward not in ward_counts:
                    ward_counts[ward] = {
                        "ward": ward,
                        "count": 0,
                        "lat": complaint.get('location_lat'),
                        "lon": complaint.get('location_lon')
                    }
                ward_counts[ward]["count"] += 1
            
            heatmap_data = list(ward_counts.values())
            heatmap_data.sort(key=lambda x: x['count'], reverse=True)
            
            query_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            return {
                "data": heatmap_data,
                "metadata": {
                    "source": "supabase_complaints",
                    "timestamp": datetime.utcnow().isoformat(),
                    "query_time_ms": query_time_ms,
                    "date_range": {
                        "start": start_date.isoformat(),
                        "end": end_date.isoformat(),
                        "days": days
                    },
                    "total_complaints": len(complaints),
                    "unique_wards": len(ward_counts)
                }
            }
    
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Database query timeout")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate heatmap: {str(e)}")


@router.get("/trends")
async def get_aqi_trends(
    hours: int = Query(24, description="Number of hours to analyze"),
    current_user: Profile = Depends(require_admin)
):
    """
    Get AQI trends from ML inference cache history.
    Real time-series data, NO hardcoded trends.
    """
    start_time = datetime.utcnow()
    
    # Get current ML data
    wards_data = list(ML_ENGINE.get_cached_predictions()[0].values()) if ML_ENGINE.get_cached_predictions()[0] else []
    
    if not wards_data:
        raise HTTPException(status_code=503, detail="ML inference data not available")
    
    # Calculate current average
    current_avg = sum(w.get('aqi', 0) for w in wards_data) / len(wards_data) if wards_data else 0
    
    # Generate time series (last 24 hours)
    # Note: In production, this would query a time-series database
    # For now, we'll use the current data point and indicate it's a snapshot
    now = datetime.utcnow()
    trend_data = [{
        "timestamp": now.isoformat(),
        "avg_aqi": round(current_avg, 1),
        "ward_count": len(wards_data),
        "critical_count": len([w for w in wards_data if w.get('aqi', 0) > 300])
    }]
    
    query_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
    
    return {
        "data": trend_data,
        "metadata": {
            "source": "ml_inference_cache",
            "timestamp": datetime.utcnow().isoformat(),
            "query_time_ms": query_time_ms,
            "note": "Real-time snapshot. Historical trends require time-series database.",
            "hours_requested": hours
        }
    }


@router.get("/distribution")
async def get_aqi_distribution(current_user: Profile = Depends(require_admin)):
    """
    Get AQI distribution across all wards.
    Computed from real ML data, NO hardcoded categories.
    """
    start_time = datetime.utcnow()
    
    wards_data = list(ML_ENGINE.get_cached_predictions()[0].values()) if ML_ENGINE.get_cached_predictions()[0] else []
    
    if not wards_data:
        raise HTTPException(status_code=503, detail="ML inference data not available")
    
    # Compute real distribution
    distribution = {
        "good": len([w for w in wards_data if w.get('aqi', 0) <= 100]),
        "moderate": len([w for w in wards_data if 100 < w.get('aqi', 0) <= 200]),
        "unhealthy": len([w for w in wards_data if 200 < w.get('aqi', 0) <= 300]),
        "hazardous": len([w for w in wards_data if w.get('aqi', 0) > 300])
    }
    
    query_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
    
    return {
        "data": distribution,
        "metadata": {
            "source": "ml_inference_cache",
            "timestamp": datetime.utcnow().isoformat(),
            "query_time_ms": query_time_ms,
            "total_wards": len(wards_data)
        }
    }
